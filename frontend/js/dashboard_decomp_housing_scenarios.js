/* Housing and scenarios: the housing spending page (rent vs own, home-sale
   assumptions, stress sell-home rows), the scenario manager (templates, saved
   scenario sets, current-override diffing), and the inactive-value reveal
   panel shared by both -- extracted from dashboard.js by
   tools/js_codemod/extract_module.mjs.

   Third domain cluster of the Wave 6.4 domain-module split (see
   docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md),
   after dashboard_decomp_assets_other.js and
   dashboard_decomp_spending_taxonomy.js. Selected as a connected component of
   dashboard.js's internal call graph (tools/js_codemod/find_clusters.mjs),
   re-run against the current file rather than trusting the previous report --
   every extraction changes the graph for the next one.

   Housing and scenarios arrive as ONE component rather than two because the
   scenario layer's whole job is overriding housing assumptions: the home-sale
   and rent rows are what scenario sets diff against, and both sides share the
   inactive-row reveal helpers. Splitting them would have put a cross-module
   edge through the middle of that relationship for no benefit.

   Loaded BEFORE dashboard.js, in the same position as the other extracted
   modules -- not after them with the leaves. dashboard.js ends its module body
   with a queueMicrotask() that schedules the real boot work, and a microtask
   checkpoint runs after that script's evaluation, so it can fire before a
   LATER module script has evaluated. This module's own top level is nothing
   but declarations and one Object.assign, so it has no evaluation-time
   dependency on dashboard.js and is safe to run first.

   SCENARIO_TEMPLATES moved with the code (read by this cluster and nothing
   else anywhere in the repo). SCENARIO_SET_STORAGE_KEY did NOT: it is also
   read by dashboard_decomp_row_model.js, so it is shared state and stays in
   dashboard.js behind its generated accessor. The codemod's variable safety
   rule refused it by name rather than letting the split quietly break it.

   What this module still reaches back into dashboard.js for, enumerated with
   tools/js_codemod/cluster_deps.mjs against the moved declarations' own text,
   so this list is exhaustive as of this pass rather than illustrative:

     - the function renderMain (a reassigned monkey-patch chain, exposed via a
       get accessor, so a bare call here gets the live decorated
       implementation);

     - one WRITTEN state variable, activeStep. It is `let` in dashboard.js and
       gets a set accessor from convert_dashboard.mjs. The bare assignment from
       inside this module is legal despite module strict mode precisely because
       the bridge has already defined the property on window: strict mode only
       throws for an identifier that resolves to nothing at all. Remove that
       setter and the assignment starts throwing at call time;

     - seven read-only bindings -- SCENARIO_SET_STORAGE_KEY, dirty,
       inactiveEditReveals, planLoaded, planSource, rows, searchText. */

export function rowIsCanonicalHomeBasis(r) {
  return (
    String(r.section || "").trim() === "Other Assets" &&
    norm(r.subsection || "") === "home" &&
    norm(r.label) === "home_basis"
  );
}

export function rowIsHomeSaleAssumption(r) {
  return rowIsBaseHomeSaleInput(r) || rowIsStressSellHomeInput(r);
}

export function rowIsEconomyScenario(r) {
  return (
    r.section === "Scenarios" &&
    ["high_inflation", "low_return"].includes(norm(r.subsection))
  );
}

export function rowValueIsMeaningful(row, state) {
  const raw = String(valOf(row) || "").trim();
  if (state && state.listAlways) return true;
  if (raw === "") return false;
  const clean = raw.replace(/[$,%\s,]/g, "").toLowerCase();
  if (["0", "0.0", "0.00", "false", "no", "none", "off"].includes(clean))
    return false;
  return true;
}

export function inactiveRowsForStep(id) {
  return rawRowsForStep(id)
    .map((r) => ({ row: r, state: rowBuildUsageState(r, id) }))
    .filter(
      (x) =>
        !x.state.active &&
        !x.state.optionalModuleOff &&
        rowValueIsMeaningful(x.row, x.state),
    );
}

export function inactiveValueDisplay(row, state = {}) {
  if (state && state.suppressValue) return "retired value ignored";
  const v = displayValueForInput(row, valOf(row));
  return v === "" ? "blank" : v;
}

export function revealInactiveRow(idx) {
  inactiveEditReveals.add(Number(idx));
  renderMain();
  setTimeout(() => {
    const el = document.querySelector(`[data-row="${idx}"]`);
    if (el) {
      el.focus();
      if (el.select) el.select();
    }
  }, 0);
}

export function inactiveValuesPanel(stepId) {
  const skip = new Set([
    "start",
    "review",
    "build_impact",
    "detailed_results",
    "assumption_signoff",
  ]);
  if (skip.has(stepId) || !planLoaded) return "";
  const items = inactiveRowsForStep(stepId);
  const title = "Inactive values";
  if (!items.length) return "";
  const rowsHtml = items
    .slice(0, 12)
    .map(({ row, state }) => {
      const action = state.noReveal
        ? `<span class="small">${esc(state.actionLabel || "Edit the active source instead")}</span>`
        : `<button class="btn" type="button" onclick="revealInactiveRow(${row.row_index})">${esc(state.actionLabel || "Edit to activate")}</button>`;
      const label = state.displayLabel || humanLabel(row.label, row);
      return `<tr><td><b>${esc(label)}</b><div class="small">${esc(friendlyGroup(row))}</div></td><td>${esc(inactiveValueDisplay(row, state))}</td><td>${esc(formatAcronyms(state.reason || "This value is currently not consumed by the build."))}</td><td>${esc(formatAcronyms(state.activation || "Change the controlling setting for this page."))}</td><td>${esc(formatAcronyms(state.effect || fieldGuidance(row).impact))}</td><td>${action}</td></tr>`;
    })
    .join("");
  const more =
    items.length > 12
      ? `<p class="small">${items.length - 12} additional inactive value${items.length - 12 === 1 ? "" : "s"} are hidden from this summary. Use page search or All assumptions to review broader configuration.</p>`
      : "";
  return `<details class="inactive-values-panel"><summary>${title}: ${items.length} saved value${items.length === 1 ? "" : "s"} not used by the next build</summary><div class="inactive-values-body"><p class="small">Inactive values are saved in Plan Data but are hidden as ordinary inputs because the current build settings will not consume them. Use the action column only when you intentionally want to change the controlling setting or value so the build starts using it.</p><div class="lot-table-wrap"><table class="lot-table inactive-values-table"><thead><tr><th>Inactive value</th><th>Saved value</th><th>Why inactive</th><th>What would activate it</th><th>Likely effect on impacts</th><th></th></tr></thead><tbody>${rowsHtml}</tbody></table></div>${more}</div></details>`;
}

export async function estimateHousingFromState(stepNum) {
  const sub = "next_step_" + stepNum;
  const stateRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "state",
  );
  const typeRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "type",
  );
  const cityTypeRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "city_type",
  );
  const popRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "population_size",
  );
  const stateVal = stateRow
    ? String(valOf(stateRow) || "")
        .trim()
        .toUpperCase()
    : "";
  const typeVal = typeRow
    ? String(valOf(typeRow) || "purchase").toLowerCase()
    : "purchase";
  const isPurchase = typeVal === "purchase";
  if (!stateVal) {
    showMessage("Enter a state abbreviation first (e.g. IL, TX, FL).", "error");
    return;
  }
  if (isPurchase && cityTypeRow && !String(valOf(cityTypeRow) || "").trim()) {
    showMessage("Select an Area Type before estimating.", "error");
    return;
  }
  if (isPurchase && popRow && !String(valOf(popRow) || "").trim()) {
    showMessage("Enter a Population before estimating.", "error");
    return;
  }
  const cityTypeVal = cityTypeRow
    ? String(valOf(cityTypeRow) || "suburban").trim()
    : "suburban";
  const popVal = popRow
    ? String(valOf(popRow) || "20000").replace(/[^0-9]/g, "")
    : "20000";
  try {
    const out = await api("/api/housing/state-estimate", {
      method: "POST",
      body: JSON.stringify({
        state: stateVal,
        step: sub,
        type: typeVal,
        city_type: cityTypeVal,
        population_size: parseInt(popVal) || 20000,
      }),
    });
    if (!out || !out.estimate) {
      showMessage("No estimate available for " + stateVal, "error");
      return;
    }
    const e = out.estimate;
    const fieldMap = {
      purchase_price: isPurchase ? e.purchase_price : null,
      monthly_rent: !isPurchase ? e.monthly_rent : null,
      insurance_annual: e.insurance_annual,
      utilities_annual: e.utilities_annual,
      maintenance_annual: isPurchase ? e.maintenance_annual : null,
      re_tax_pct: isPurchase ? e.re_tax_pct : null,
      hoa_pct: isPurchase ? e.hoa_pct : null,
      mortgage_rate_pct: isPurchase ? e.mortgage_rate_pct : null,
    };
    // #266: cache for per-field restoreHousingEstimateField() below.
    window.housingLastEstimate[stepNum] = fieldMap;
    let applied = 0;
    for (const label of Object.keys(fieldMap)) {
      if (window.applyHousingEstimateField(stepNum, label, fieldMap[label])) applied++;
    }
    renderMain();
    showMessage(
      "Estimated values applied for " +
        stateVal +
        " (" +
        applied +
        " fields). Review and adjust as needed.",
    );
  } catch (err) {
    showMessage("Error fetching estimate: " + err.message, "error");
  }
}

// #298: utilities/maintenance/insurance were entered once against a home
// value or rent and then left stale after the user changed that value or
// rent -- nothing recomputed them. When purchase_price or monthly_rent on a
// Next Housing Step changes, scale the sibling utilities/maintenance/(for a
// purchase) insurance figures by the same ratio the value/rent itself moved,
// rather than re-querying state defaults (estimateHousingFromState above
// would overwrite the price/rent the user just typed with a state lookup).
export function reestimateHousingCostsOnValueChange(row, oldStored, newStored) {
  if (!row || row.section !== "Housing") return 0;
  const sub = norm(row.subsection || "");
  if (!/^next_step_\d+$/.test(sub)) return 0;
  const label = norm(row.label);
  if (label !== "purchase_price" && label !== "monthly_rent") return 0;
  const oldVal = numberFromDisplay(oldStored);
  const newVal = numberFromDisplay(newStored);
  if (!(oldVal > 0) || !(newVal > 0) || oldVal === newVal) return 0;
  const ratio = newVal / oldVal;
  const targets =
    label === "purchase_price"
      ? ["insurance_annual", "utilities_annual", "maintenance_annual"]
      : ["insurance_annual", "utilities_annual"];
  let adjusted = 0;
  targets.forEach((lbl) => {
    const r = rows.find(
      (x) =>
        x.section === "Housing" &&
        norm(x.subsection || "") === sub &&
        norm(x.label) === lbl,
    );
    if (!r) return;
    const cur = numberFromDisplay(valOf(r));
    if (!(cur > 0)) return;
    const next = Math.round(cur * ratio);
    if (next === cur) return;
    editValue(r.row_index, String(next), null);
    adjusted++;
  });
  return adjusted;
}

export function housingRentMonthlyValue() {
  const rentLabels = new Set(["monthly_rent"]);
  let maxRent = 0;
  (rows || []).forEach(function (r) {
    const lbl = norm((r && r.label) || "");
    if (rentLabels.has(lbl)) {
      const n = numberFromDisplay(valOf(r));
      if (n !== null && n > maxRent) maxRent = n;
    }
  });
  return maxRent;
}

export function housingRentIsConfigured() {
  return housingRentMonthlyValue() > 0;
}

export function rowIsRentInput(r) {
  const l = norm((r && r.label) || "");
  return l === "monthly_rent";
}

export function housingAreaTypeSelect(row) {
  const cur = String(valOf(row) || "")
    .trim()
    .toLowerCase();
  const opts = ["urban", "suburban", "rural"];
  return `<select data-row="${row.row_index}" onchange="editValue(${row.row_index},this.value,this)" onfocus="showFieldHelp(${row.row_index})"><option value="">Select area type</option>${opts.map((o) => `<option value="${o}" ${norm(o) === norm(cur) ? "selected" : ""}>${titleWord(o)}</option>`).join("")}</select>`;
}

export async function clearHousingNextStep(stepNum) {
  if (
    !(await showInAppConfirm(
      "All fields in Next Step " + stepNum + " will be reset.",
      { title: "Clear Next Step", confirmLabel: "Clear", variant: "warn" },
    ))
  )
    return;
  var sub = "next_step_" + stepNum;
  rows
    .filter(function (r) {
      return r.section === "Housing" && norm(r.subsection || "") === sub;
    })
    .forEach(function (r) {
      dirty.set(r.row_index, "");
    });
  renderMain();
}

export function renderNextHousingStepSection(stepRows, stepLabel, stepNum) {
  if (!stepRows || !stepRows.length) return "";
  var typeRow = stepRows.find(function (r) {
    return norm(r.label) === "type";
  });
  var typeVal = typeRow
    ? String(valOf(typeRow) || "purchase").toLowerCase()
    : "purchase";
  var isPurchase = typeVal !== "rent";
  var stateRow = stepRows.find(function (r) {
    return norm(r.label) === "state";
  });
  var cityTypeRow = stepRows.find(function (r) {
    return norm(r.label) === "city_type";
  });
  var popRow = stepRows.find(function (r) {
    return norm(r.label) === "population_size";
  });
  var stateVal = stateRow ? String(valOf(stateRow) || "").trim() : "";
  var cityTypeVal = cityTypeRow ? String(valOf(cityTypeRow) || "").trim() : "";
  var popVal = popRow ? String(valOf(popRow) || "").trim() : "";

  // Purchase: State → Area Type → Population → [Estimate] → remaining fields
  // Rent: State → [Estimate] → remaining fields (no Area Type, Population, or HOA)
  var PURCHASE_FIRST = ["state", "city_type", "population_size"];
  var PURCHASE_REST = [
    "start_year",
    "end_year",
    "purchase_price",
    "down_payment",
    "mortgage_rate_pct",
    "insurance_annual",
    "utilities_annual",
    "maintenance_annual",
    "re_tax_pct",
    "hoa_pct",
  ];
  var RENT_FIRST = ["state"];
  var RENT_REST = [
    "start_year",
    "end_year",
    "monthly_rent",
    "insurance_annual",
    "utilities_annual",
  ];

  function pickRows(labels) {
    var out = [];
    labels.forEach(function (lbl) {
      var r = stepRows.find(function (x) {
        return norm(x.label) === lbl && x !== typeRow;
      });
      if (r) out.push(r);
    });
    return out;
  }
  var firstRows = pickRows(isPurchase ? PURCHASE_FIRST : RENT_FIRST);
  var restRows = pickRows(isPurchase ? PURCHASE_REST : RENT_REST);

  // Estimate button: Purchase requires all 3 inputs; Rent requires state only
  var estimateReady = isPurchase
    ? stateVal && cityTypeVal && popVal
    : !!stateVal;
  var estimateHint = isPurchase
    ? "Enter State, Area Type, and Population to enable"
    : "Enter State to enable";
  var estimateBtn =
    '<div class="section-note" style="margin-top:4px;margin-bottom:8px">' +
    '<button class="btn btn-sm" type="button" data-requires-app="1"' +
    (estimateReady ? "" : ' disabled title="' + estimateHint + '"') +
    ' onclick="estimateHousingFromState(' +
    stepNum +
    ')">' +
    "Estimate fields" +
    (stateVal ? " (" + esc(stateVal.toUpperCase()) + ")" : "") +
    "</button>" +
    ' <span class="small">Fills typical ' +
    (isPurchase ? "purchase" : "rental") +
    " costs for a 3BR/2BA home with at least a 40×40 ft backyard. All values are editable.</span></div>";
  // #266: per-field restore-to-estimate links.
  var restoreFieldLabels = { insurance_annual: "Insurance", utilities_annual: "Utilities", maintenance_annual: "Maintenance", re_tax_pct: "RE Tax %", hoa_pct: "HOA %" };
  var cachedEst = window.housingLastEstimate[stepNum];
  if (cachedEst) {
    var restoreLinks = Object.keys(restoreFieldLabels)
      .filter((lbl) => cachedEst[lbl] !== null && cachedEst[lbl] !== undefined)
      .map((lbl) => '<button class="btn tiny" type="button" onclick="restoreHousingEstimateField(' + stepNum + ",'" + lbl + '\')">↺ ' + esc(restoreFieldLabels[lbl]) + "</button>")
      .join(" ");
    if (restoreLinks) estimateBtn += '<div class="section-note small" style="margin-bottom:8px">Restore app estimate for one field: ' + restoreLinks + "</div>";
  }

  var typeToggle = "";
  if (typeRow) {
    typeToggle =
      '<div class="field housing-type-field"><div class="field-label">Rent or Buy</div>' +
      '<div class="btn-toggle-group">' +
      '<button type="button" class="btn-toggle' +
      (isPurchase ? " active" : "") +
      '" onclick="editValue(' +
      typeRow.row_index +
      ",'purchase',null);renderMain()\">Buy</button>" +
      '<button type="button" class="btn-toggle' +
      (!isPurchase ? " active" : "") +
      '" onclick="editValue(' +
      typeRow.row_index +
      ",'rent',null);renderMain()\">Rent</button>" +
      '</div><div class="field-hint">Choose whether this housing step is a purchase or a rental. Rent stays visible even when the saved rent amount is currently zero.</div></div>';
  }

  var html =
    '<details><summary class="section-header">' +
    esc(stepLabel) +
    '</summary><div class="section-body">';
  html +=
    '<button class="btn danger" type="button" onclick="clearHousingNextStep(' +
    stepNum +
    ')">Clear This Step</button>';
  html += typeToggle;
  if (firstRows.length)
    html +=
      '<div class="field-list">' +
      firstRows
        .map(function (r) {
          return norm(r.label) === "city_type"
            ? '<div class="field"><div class="field-label">Area Type</div>' +
                housingAreaTypeSelect(r) +
                "</div>"
            : fieldHtml(r);
        })
        .join("") +
      "</div>";
  html += estimateBtn;
  if (restRows.length)
    html +=
      '<div class="field-list">' + restRows.map(fieldHtml).join("") + "</div>";
  html += "</div></details>";
  return html;
}

export function renderCollapsibleDomainBudgetSection(domain, openByDefault) {
  const title = domainBudgetTitle(domain);
  return `<details class="domain-budget-section" data-dkey="domain-budget:${esc(domain)}"><summary class="section-header">${esc(title)}</summary><div class="section-body">${renderDomainBudgetPage(domain, { embedded: true })}</div></details>`;
}

export function renderSpendingHousing() {
  const rs = rowsForStep("spending_mortgage_events");
  const _CURRENT_MORTGAGE_EXCL = ["annual_real_estate_taxes"];
  const mortgage = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Cashflow" &&
      norm(r.subsection || "") === "mortgage" &&
      !_CURRENT_MORTGAGE_EXCL.includes(norm(r.label || "")),
  );
  const homeRows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Other Assets" &&
      norm(r.subsection || "") === "home",
  );
  const _CURRENT_HOME_EXCL = [
    "city_type",
    "population_size",
    "hoa_pct",
    "hoa_annual",
    "homeowners_insurance_annual",
    "home_maintenance_annual",
    "utilities_annual",
  ];
  const housingOpRows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "current_home" &&
      !_CURRENT_HOME_EXCL.includes(norm(r.label || "")),
  );
  const homeImprovRows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "home_improvements",
  );
  const nextStep1Rows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "next_step_1",
  );
  const nextStep2Rows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "next_step_2",
  );
  const keyHomeRows = homeRows.filter((r) => {
    const l = norm(r.label || "");
    return homeValueLabelIsCanonical(r.label) || l === "home_basis";
  });

  // Determine if any next housing step is a Purchase — home improvements only show then.
  const nextStep1TypeRow = nextStep1Rows.find((r) => norm(r.label) === "type");
  const nextStep2TypeRow = nextStep2Rows.find((r) => norm(r.label) === "type");
  const nextStep1IsBuy =
    !nextStep1TypeRow ||
    String(valOf(nextStep1TypeRow) || "purchase").toLowerCase() === "purchase";
  const nextStep2IsBuy =
    !nextStep2TypeRow ||
    String(valOf(nextStep2TypeRow) || "purchase").toLowerCase() === "purchase";
  const anyNextStepIsBuy = nextStep1IsBuy || nextStep2IsBuy;

  let html = "";

  html += renderCollapsibleDomainBudgetSection("housing", true);

  html +=
    '<details><summary class="section-header">Current home</summary><div class="section-body">';
  html +=
    '<div class="section-note">Current mortgage payment timing and home value. Real-estate taxes, homeowners insurance, maintenance, and utilities are entered in Housing Budget Detail below. Click <button class="btn btn-sm" type="button" onclick="seedHousingRows()">Seed Housing Fields</button> to add insurance, utilities, maintenance, and next-housing-step fields if not yet present.</div>';
  if (mortgage.length)
    html +=
      '<div class="field-list">' + mortgage.map(fieldHtml).join("") + "</div>";
  if (housingOpRows.length)
    html +=
      '<div class="field-list">' +
      housingOpRows.map(fieldHtml).join("") +
      "</div>";
  if (keyHomeRows.length)
    html +=
      '<div class="field-list">' +
      keyHomeRows.map(fieldHtml).join("") +
      "</div>";
  html += "</div></details>";

  html += renderBaseHomeSaleRows(rs);

  if (nextStep1Rows.length) {
    html += renderNextHousingStepSection(
      nextStep1Rows,
      "Next Housing Step 1",
      1,
    );
  }
  if (nextStep2Rows.length) {
    html += renderNextHousingStepSection(
      nextStep2Rows,
      "Next Housing Step 2",
      2,
    );
  }
  if (!nextStep1Rows.length && !nextStep2Rows.length) {
    html +=
      '<details><summary class="section-header">Next Housing Step (Purchase)</summary><div class="section-body">';
    html +=
      '<div class="section-note">Next-step housing fields not found. Click <button class="btn btn-sm" type="button" onclick="seedHousingRows()">Seed Housing Fields</button> to add fields for future housing steps.</div>';
    html += "</div></details>";
  }

  // Home improvement projects — only relevant for purchase (not rent).
  if (homeImprovRows.length && anyNextStepIsBuy) {
    html +=
      '<details><summary class="section-header">Home improvement projects</summary><div class="section-body">';
    html +=
      '<div class="section-note">Planned improvement costs are entered here as part of Housing. Other pages may reference them read-only.</div>';
    html +=
      '<div class="field-list">' +
      homeImprovRows.map(fieldHtml).join("") +
      "</div>";
    html += "</div></details>";
  }

  return html;
}

export function homeSaleScenarioYearRow(home) {
  return (
    home.find(
      (r) =>
        String(r.section || "").trim() === "Scenarios" &&
        norm(r.subsection) === "sell_home" &&
        (norm(r.label) === "home_sale_year" ||
          norm(r.label) === "planned_home_sale_year"),
    ) ||
    home.find(
      (r) =>
        norm(r.label) === "home_sale_year" ||
        norm(r.label) === "planned_home_sale_year",
    )
  );
}

export function addUniqueRow(target, row) {
  if (row && !target.includes(row)) target.push(row);
}

export function renderBaseHomeSaleRows(rs) {
  const base = rs
    .filter(rowIsBaseHomeSaleInput)
    .filter((r) => !rowIsRetiredScenarioHomeDuplicate(r));
  if (!base.length) return "";
  const year = base.find(
    (r) =>
      String(r.section || "").trim() === "Other Assets" &&
      norm(r.subsection) === "home" &&
      norm(r.label) === "home_sale_year",
  );
  const currentYear = new Date().getFullYear();
  const yearNum = year
    ? Number(String(valOf(year) || "0").replace(/[^0-9]/g, "")) || 0
    : 0;
  const active = yearNum >= currentYear; // Year always first; remaining fields only when a year is entered
  let yearFirst = [year].filter(Boolean);
  let restVisible = [];
  if (active) {
    base
      .filter(
        (r) =>
          r !== year &&
          !rowIsCanonicalHomeValue(r) &&
          !rowIsCanonicalHomeBasis(r),
      )
      .forEach((r) => {
        if (!restVisible.includes(r)) restVisible.push(r);
      });
  }
  const introNote = active
    ? '<div class="section-note">Sale year set — enter sale price, commission, and related details. Home value and basis are managed in Current Home above.</div>'
    : '<div class="section-note">Enter a home sale year to reveal sale detail fields.</div>';
  return `<details><summary class="section-header">Home Sale</summary><div class="field-list">${introNote}${yearFirst.map(fieldHtml).join("")}${restVisible.map(fieldHtml).join("")}</div>${active ? renderHomeSaleSplits() : ""}</details>`;
}

export function renderStressSellHomeRows(rs) {
  const stress = rs.filter(rowIsStressSellHomeInput);
  if (!stress.length) return "";
  const year = homeSaleScenarioYearRow(stress);
  const active = year && (Number(currencyRaw(valOf(year) || 0)) || 0) > 0;
  const canonicalValue = rs.find(rowIsCanonicalHomeValue);
  const canonicalBasis = rs.find(rowIsCanonicalHomeBasis);
  let visible = [];
  addUniqueRow(visible, canonicalValue);
  addUniqueRow(visible, canonicalBasis);
  if (active)
    stress
      .filter((r) => housingRentIsConfigured() || !rowIsRentInput(r))
      .forEach((r) => addUniqueRow(visible, r));
  else
    addUniqueRow(
      visible,
      year || stress.find((r) => norm(r.label).includes("home_sale_year")),
    );
  return `<details><summary>Sell Home stress test — scenario sheet only</summary><div class="field-list"><div class="section-note warning"><b>Scenario-only:</b> these Sell Home stress-test rows are used by the Scenario Analysis workbook sheet, but they do <b>not</b> change the base-plan Build Impact cards. To change headline terminal net worth, set the Base Plan Home Sale Year above. The Home Value and Home Basis shown here are shared canonical Home asset facts. The sale value used by this stress test is projected from canonical Home Value and appreciation.</div>${sortRowsByDependency(visible).map(fieldHtml).join("")}</div></details>`;
}

// Ticket 286: Scenarios shows the STRESS home-sale panel only. It used to also
// render renderBaseHomeSaleRows() -- byte-identical to the panel the Housing
// page already owns (renderSpendingHousing, ~line 513) -- so the same
// home_sale_year/price fields were editable on two pages with no indication
// they were the same plan values. Housing is the single home for base-plan
// home-sale input; Scenarios keeps only the stress variant, which drives
// scenario sheets rather than the base projection.
export function renderHomeSaleScenarioRows(rs) {
  if (!rs.some(rowIsStressSellHomeInput)) return "";
  return renderStressSellHomeRows(rs);
}

export const SCENARIO_TEMPLATES = [
  {
    id: "conservative_markets",
    title: "Conservative markets",
    desc: "Raise inflation and lower portfolio return, then include both shocks in the combined stress test.",
    changes: [
      {
        subsection: "High Inflation",
        label: "inflation_override",
        value: "4.50%",
        why: "Tests sustained purchasing-power pressure.",
      },
      {
        subsection: "Low Return",
        label: "portfolio_return_override",
        value: "4.00%",
        why: "Tests lower expected portfolio growth.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_high_inflation",
        value: "TRUE",
        why: "Includes inflation in the combined stress case.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_low_return",
        value: "TRUE",
        why: "Includes low returns in the combined stress case.",
      },
    ],
  },
  {
    id: "spending_pressure",
    title: "Spending pressure",
    desc: "Model a higher-spending case and include it in the combined stress test.",
    changes: [
      {
        subsection: "Higher Spending",
        label: "spend_multiplier",
        value: "1.20",
        why: "Increases scenario spending by 20%.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_spend_more",
        value: "TRUE",
        why: "Includes the higher-spending case in the combined stress test.",
      },
    ],
  },
  {
    id: "retire_later_income",
    title: "Retire later bridge",
    desc: "Turn on the retire-later scenario with continued earned income assumptions.",
    changes: [
      {
        subsection: "Retire Later",
        label: "member_1_retire_year",
        value: "2029",
        why: "Moves the scenario retirement year later.",
      },
      {
        subsection: "Retire Later",
        label: "salary_override",
        value: "$50,000",
        why: "Adds scenario earned income during the bridge period.",
      },
      {
        subsection: "Retire Later",
        label: "income_growth_rate_override",
        value: "0.00%",
        why: "Keeps the bridge-income case easy to read.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_retire_later",
        value: "TRUE",
        why: "Includes retire-later in the combined case.",
      },
    ],
  },
  {
    id: "home_sale_liquidity",
    title: "Home-sale liquidity",
    desc: "Turn on the Sell Home stress case and include it in the combined stress test.",
    changes: [
      {
        subsection: "Sell Home",
        label: "home_sale_year",
        value: "2045",
        why: "Activates the scenario-only home sale timing.",
      },
      {
        subsection: "Sell Home",
        label: "home_sale_proceeds_account",
        value: "Member_2_Trust",
        why: "Routes proceeds to the configured account for the stress case.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_sell_home",
        value: "TRUE",
        why: "Includes home sale in the combined case.",
      },
    ],
  },
];

export function scenarioTemplateById(id) {
  return SCENARIO_TEMPLATES.find((t) => t.id === id) || null;
}

export function scenarioWriteSets(list) {
  try {
    localStorage.setItem(
      SCENARIO_SET_STORAGE_KEY,
      JSON.stringify((list || []).slice(0, 20)),
    );
    return true;
  } catch (e) {
    showMessage("Could not save scenario set locally: " + e.message, "error");
    return false;
  }
}

export function scenarioCurrentItems() {
  const seen = new Set();
  return scenarioRowsForManagement(rawRowsForStep("scenarios"))
    .filter((r) => {
      const k = scenarioRowKey(r);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .map((r) => ({
      key: scenarioRowKey(r),
      section: r.section,
      subsection: r.subsection,
      label: r.label,
      value: String(valOf(r) || ""),
      display_value: displayValueForInput(r, valOf(r) || ""),
      name: scenarioFieldName(r),
    }));
}

export function scenarioActiveOverrideItems(rs) {
  return scenarioRowsForManagement(rs)
    .filter((r) => rowValueIsMeaningful(r) && norm(r.subsection) !== "base")
    .map((r) => ({
      key: scenarioRowKey(r),
      subsection: r.subsection,
      label: humanLabel(r.label, r),
      value: displayValueForInput(r, valOf(r) || ""),
      group: friendlyGroup(r),
    }));
}

export function scenarioSetDiffItems(set) {
  const map = {};
  scenarioRowsForManagement(rawRowsForStep("scenarios")).forEach((r) => {
    map[scenarioRowKey(r)] = r;
  });
  return (set.items || [])
    .map((item) => {
      const r = map[item.key] || scenarioFindRow(item.subsection, item.label);
      if (!r)
        return {
          name: item.name || `${item.subsection} · ${item.label}`,
          current: "Not found",
          saved: item.display_value || item.value || "",
          missing: true,
        };
      const cur = displayValueForInput(r, valOf(r) || "");
      const saved = displayValueForInput(r, item.value || "");
      return {
        name: item.name || scenarioFieldName(r),
        current: cur || "blank",
        saved: saved || "blank",
        changed: String(cur) !== String(saved),
      };
    })
    .filter((x) => x.changed || x.missing);
}

export function scenarioDiffTableHtml(items, emptyText) {
  const list = (items || []).slice(0, 10);
  if (!list.length)
    return `<p class="small">${esc(emptyText || "No differences from the current scenario values.")}</p>`;
  let html =
    '<table class="lot-table scenario-diff-table"><thead><tr><th>Assumption</th><th>Current</th><th>Saved / template</th></tr></thead><tbody>';
  list.forEach((x) => {
    html += `<tr><td>${esc(x.name || `${x.group || ""} ${x.label || ""}`)}</td><td>${esc(x.current || "blank")}</td><td>${esc(x.saved || x.value || "blank")}</td></tr>`;
  });
  html += "</tbody></table>";
  if ((items || []).length > list.length)
    html += `<p class="small">+${(items || []).length - list.length} additional difference${(items || []).length - list.length === 1 ? "" : "s"}.</p>`;
  return html;
}

export function scenarioTemplateDiffItems(tpl) {
  return (tpl.changes || []).map((c) => {
    const r = scenarioFindRow(c.subsection, c.label);
    return {
      name: r ? scenarioFieldName(r) : `${c.subsection} · ${c.label}`,
      current: r ? displayValueForInput(r, valOf(r) || "") : "Not found",
      saved: c.value || "",
      changed: true,
    };
  });
}

export function applyScenarioTemplate(id) {
  const tpl = scenarioTemplateById(id);
  if (!tpl) return;
  let applied = 0,
    missing = [];
  (tpl.changes || []).forEach((c) => {
    const r = scenarioFindRow(c.subsection, c.label);
    if (!r) {
      missing.push(`${c.subsection} / ${c.label}`);
      return;
    }
    editValue(r.row_index, c.value, null);
    applied++;
  });
  renderMain();
  showMessage(
    `${tpl.title} template applied to ${applied} scenario assumption${applied === 1 ? "" : "s"}${missing.length ? "; " + missing.length + " field(s) were not found." : ""}`,
  );
}

export async function saveCurrentScenarioSet() {
  const name = await showInAppPrompt("Name this scenario set:", "", {
    title: "Save Scenario Set",
  });
  if (!name || !name.trim()) return;
  const items = scenarioCurrentItems();
  const set = {
    id: "scen_" + Date.now(),
    schema: "scenario_set_v1",
    name: name.trim(),
    created_at: new Date().toISOString(),
    items,
  };
  const sets = scenarioStoredSets().filter((s) => s.name !== set.name);
  sets.unshift(set);
  if (scenarioWriteSets(sets)) {
    showMessage("Scenario set saved locally.");
    renderMain();
  }
}

export function applySavedScenarioSet(id) {
  const set = scenarioStoredSets().find((s) => s.id === id);
  if (!set) return;
  let applied = 0,
    missing = 0;
  (set.items || []).forEach((item) => {
    const r =
      scenarioRowsForManagement(rawRowsForStep("scenarios")).find(
        (x) => scenarioRowKey(x) === item.key,
      ) || scenarioFindRow(item.subsection, item.label);
    if (!r) {
      missing++;
      return;
    }
    editValue(r.row_index, item.value || "", null);
    applied++;
  });
  renderMain();
  showMessage(
    `Applied saved scenario set "${set.name}" to ${applied} assumption${applied === 1 ? "" : "s"}${missing ? "; " + missing + " saved field(s) were not found." : ""}`,
  );
}

export async function deleteSavedScenarioSet(id) {
  const sets = scenarioStoredSets();
  const set = sets.find((s) => s.id === id);
  if (!set) return;
  if (
    !(await showInAppConfirm(
      '"' + set.name + '" will be permanently removed.',
      {
        title: "Delete Scenario Set",
        confirmLabel: "Delete",
        variant: "danger",
      },
    ))
  )
    return;
  if (scenarioWriteSets(sets.filter((s) => s.id !== id))) {
    showMessage("Scenario set deleted.");
    renderMain();
  }
}

export function renderScenarioTemplatesHtml() {
  let html = '<div class="scenario-template-grid">';
  SCENARIO_TEMPLATES.forEach((t) => {
    html += `<div class="scenario-template-card"><div><h4>${esc(t.title)}</h4><p class="small">${esc(t.desc)}</p></div>${scenarioDiffTableHtml(scenarioTemplateDiffItems(t), "Template assumptions are already set this way.")}<button class="btn" type="button" onclick="applyScenarioTemplate('${escJs(t.id)}')">Apply template</button></div>`;
  });
  html += "</div>";
  return html;
}

export function renderSavedScenarioSetsHtml() {
  const sets = scenarioStoredSets();
  if (!sets.length)
    return '<p class="small">No saved scenario sets yet. Save the current scenario assumptions when you want a reusable package of what-if overrides.</p>';
  let html = '<div class="scenario-set-list">';
  sets.forEach((set) => {
    const diffs = scenarioSetDiffItems(set);
    const date = set.created_at
      ? new Date(set.created_at).toLocaleString()
      : "";
    html += `<details class="scenario-set-card"><summary><b>${esc(set.name)}</b><span>${esc(date)} · ${(set.items || []).length} assumption${(set.items || []).length === 1 ? "" : "s"}</span></summary><div class="scenario-set-body">${scenarioDiffTableHtml(diffs, "This saved set matches the current scenario assumptions.")}<div class="table-actions"><button class="btn" type="button" onclick="applySavedScenarioSet('${escJs(set.id)}')">Apply saved set</button><button class="danger-link" type="button" onclick="deleteSavedScenarioSet('${escJs(set.id)}')">Delete</button></div></div></details>`;
  });
  html += "</div>";
  return html;
}

export function renderCurrentScenarioOverridesHtml(rs) {
  const items = scenarioActiveOverrideItems(rs);
  if (!items.length)
    return '<p class="small">No active scenario-only overrides have meaningful values yet.</p>';
  let html =
    '<table class="lot-table scenario-overrides-table"><thead><tr><th>Scenario</th><th>Assumption</th><th>Current value</th></tr></thead><tbody>';
  items.slice(0, 16).forEach((x) => {
    html += `<tr><td>${esc(x.group)}</td><td>${esc(x.label)}</td><td>${esc(x.value)}</td></tr>`;
  });
  html += "</tbody></table>";
  if (items.length > 16)
    html += `<p class="small">+${items.length - 16} additional active override${items.length - 16 === 1 ? "" : "s"}.</p>`;
  return html;
}

export function renderScenarioManagementPanel(rs) {
  return `<section class="scenario-management"><div class="scenario-management-head"><div><span class="eyebrow">Planning Workbench</span><h3>Scenario Change Sets</h3><p class="small">Templates stage common deterministic what-if overrides. Saved sets are browser-local change sets; review the diff, apply a set, then Save Changes, rebuild, and compare in the Planning Workbench.</p></div><button class="btn primary" type="button" onclick="saveCurrentScenarioSet()">Save current scenario set</button></div><details><summary>Scenario templates</summary>${renderScenarioTemplatesHtml()}</details><details><summary>Saved named scenario sets</summary>${renderSavedScenarioSetsHtml()}</details><details><summary>Current scenario overrides</summary>${renderCurrentScenarioOverridesHtml(rs)}</details></section>`;
}

export function renderScenarios() {
  if (searchText.trim()) return renderFields("scenarios");
  const rs = rowsForStep("scenarios");
  const economy = rs.filter(rowIsEconomyScenario);
  const stateComp = rs.filter(
    (r) => String(r.section || "").trim() === "State Comparison",
  );
  const homeSale = rs.filter((r) => rowIsHomeSaleAssumption(r));
  const other = rs.filter(
    (r) =>
      !rowIsEconomyScenario(r) &&
      !homeSale.includes(r) &&
      !stateComp.includes(r),
  );
  let html = `<div class="field-list"><div class="section-note"><b>Scenario Change Sets are deterministic planning cases.</b> Use the Stress Suite & Monte Carlo page for probabilistic or adverse-assumption testing. Economy shocks and scenario enable/year controls are grouped first because they determine which dependent assumptions matter. Home sale here is the stress-test panel only, affecting scenario sheets; the base-plan home sale is entered once on the Housing page under Spending.</div></div>`;
  html += renderScenarioManagementPanel(rs);
  html += economy.length
    ? `<details><summary>Economy</summary><div class="field-list">${sortRowsByDependency(economy).map(fieldHtml).join("")}</div></details>`
    : "";
  html += renderHomeSaleScenarioRows(rs);
  if (stateComp.length) {
    const hwRows = stateComp.filter(
      (r) => norm(r.subsection || "") === "homeowners_insurance",
    );
    const autoRows = stateComp.filter(
      (r) => norm(r.subsection || "") === "auto_insurance",
    );
    html += `<details><summary>State comparison — insurance costs</summary><div class="field-list"><div class="section-note">Compare insurance costs between your current state (baseline) and a target relocation state. These are reference inputs only — they do not feed the projection model but appear in the scenario outputs for advisor review.</div>`;
    if (hwRows.length) {
      html += `<div class="subsection-label">Homeowners insurance</div>`;
      html += hwRows.map(fieldHtml).join("");
    }
    if (autoRows.length) {
      html += `<div class="subsection-label">Auto insurance</div>`;
      html += autoRows.map(fieldHtml).join("");
    }
    html += `</div></details>`;
  }
  html += renderFieldGroups(other);
  return html;
}

export async function seedHousingRows() {
  try {
    const resp = await api("/api/housing/seed", { method: "POST" });
    if (resp && resp.seeded !== undefined) {
      await loadAll({ source: planSource, preferLocal: false, silent: true });
      activeStep = "spending_mortgage_events";
      renderMain();
      showMessage(
        "Housing fields added (" +
          resp.seeded +
          " rows). Save Changes to persist.",
      );
    } else {
      showMessage("Housing seed returned unexpected response.", "warn");
    }
  } catch (e) {
    showMessage("Error seeding housing fields: " + e.message, "error");
  }
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  rowIsCanonicalHomeBasis,
  rowIsHomeSaleAssumption,
  rowIsEconomyScenario,
  rowValueIsMeaningful,
  inactiveRowsForStep,
  inactiveValueDisplay,
  revealInactiveRow,
  inactiveValuesPanel,
  estimateHousingFromState,
  reestimateHousingCostsOnValueChange,
  housingRentMonthlyValue,
  housingRentIsConfigured,
  rowIsRentInput,
  housingAreaTypeSelect,
  clearHousingNextStep,
  renderNextHousingStepSection,
  renderCollapsibleDomainBudgetSection,
  renderSpendingHousing,
  homeSaleScenarioYearRow,
  addUniqueRow,
  renderBaseHomeSaleRows,
  renderStressSellHomeRows,
  renderHomeSaleScenarioRows,
  SCENARIO_TEMPLATES,
  scenarioTemplateById,
  scenarioWriteSets,
  scenarioCurrentItems,
  scenarioActiveOverrideItems,
  scenarioSetDiffItems,
  scenarioDiffTableHtml,
  scenarioTemplateDiffItems,
  applyScenarioTemplate,
  saveCurrentScenarioSet,
  applySavedScenarioSet,
  deleteSavedScenarioSet,
  renderScenarioTemplatesHtml,
  renderSavedScenarioSetsHtml,
  renderCurrentScenarioOverridesHtml,
  renderScenarioManagementPanel,
  renderScenarios,
  seedHousingRows,
});
