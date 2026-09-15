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
  const startYearRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "start_year",
  );
  // Same accessor pattern displayValueForInput/valueKind use elsewhere for a
  // "percent" field: the row stores the percentage on a 0-100 scale (e.g.
  // "3.00%" -> 3), so divide by 100 to get the fraction rate the backend's
  // (1 + rate) ** years_out translation (design doc §3.2) expects.
  const homeApprRow = rows.find(
    (r) => r.section === "Other Assets" && norm(r.subsection || "") === "home" && norm(r.label) === "appreciation_rate",
  );
  const inflationRow = rows.find(
    (r) => r.section === "Economic Assumptions" && norm(r.label) === "inflation_general",
  );
  const bedroomsRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "bedrooms",
  );
  const bathroomsRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "bathrooms",
  );
  const propertyTypeRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "property_type",
  );
  const sqftBandRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "sqft_band",
  );
  const builtWithinYearsRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "built_within_years",
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
  // Area Type and Population are required for both purchase and rent -- the
  // rent estimate used to silently assume suburban/20,000 (see
  // housing-estimate-realism-and-dollar-convention-design.md §3.4).
  if (cityTypeRow && !String(valOf(cityTypeRow) || "").trim()) {
    showMessage("Select an Area Type before estimating.", "error");
    return;
  }
  if (popRow && !String(valOf(popRow) || "").trim()) {
    showMessage("Enter a Population before estimating.", "error");
    return;
  }
  const cityTypeVal = cityTypeRow
    ? String(valOf(cityTypeRow) || "suburban").trim()
    : "suburban";
  const popVal = popRow
    ? String(valOf(popRow) || "20000").replace(/[^0-9]/g, "")
    : "20000";
  const startYearVal = startYearRow
    ? parseInt(String(valOf(startYearRow) || "").replace(/[^0-9]/g, ""), 10)
    : NaN;
  const homeApprVal = homeApprRow
    ? numberFromDisplay(valOf(homeApprRow)) / 100
    : null;
  const inflationVal = inflationRow
    ? numberFromDisplay(valOf(inflationRow)) / 100
    : null;
  const bedroomsVal = bedroomsRow ? String(valOf(bedroomsRow) || "3").trim() : "3";
  const bathroomsVal = bathroomsRow ? String(valOf(bathroomsRow) || "2").trim() : "2";
  const propertyTypeVal = propertyTypeRow
    ? String(valOf(propertyTypeRow) || "single_family").trim()
    : "single_family";
  const sqftBandVal = sqftBandRow
    ? String(valOf(sqftBandRow) || "1800_2500").trim()
    : "1800_2500";
  const builtWithinYearsVal = builtWithinYearsRow
    ? String(valOf(builtWithinYearsRow) || "").trim()
    : "";
  try {
    const out = await api("/api/housing/state-estimate", {
      method: "POST",
      body: JSON.stringify({
        state: stateVal,
        step: sub,
        type: typeVal,
        city_type: cityTypeVal,
        population_size: parseInt(popVal) || 20000,
        start_year: Number.isFinite(startYearVal) ? startYearVal : "",
        home_appr: homeApprVal,
        inflation_general: inflationVal,
        bedrooms: bedroomsVal,
        bathrooms: bathroomsVal,
        property_type: propertyTypeVal,
        sqft_band: sqftBandVal,
        built_within_years: builtWithinYearsVal,
      }),
    });
    if (!out || !out.estimate) {
      showMessage("No estimate available for " + stateVal, "error");
      return;
    }
    const e = out.estimate;
    const priceLabel = isPurchase ? "purchase_price" : "monthly_rent";
    const priceRow = rows.find(
      (r) =>
        r.section === "Housing" &&
        norm(r.subsection || "") === sub &&
        norm(r.label) === priceLabel,
    );
    const priceWasUserEdited = housingPriceWasUserEdited(
      window.housingLastEstimate[stepNum] || null,
      priceLabel,
      priceRow ? valOf(priceRow) : null,
    );
    const rawFieldMap = {
      purchase_price: isPurchase ? e.purchase_price : null,
      monthly_rent: !isPurchase ? e.monthly_rent : null,
      insurance_annual: e.insurance_annual,
      utilities_annual: e.utilities_annual,
      maintenance_annual: isPurchase ? e.maintenance_annual : null,
      re_tax_pct: isPurchase ? e.re_tax_pct : null,
      hoa_pct: isPurchase ? e.hoa_pct : null,
      mortgage_rate_pct: isPurchase ? e.mortgage_rate_pct : null,
    };
    // #266: cache holds the fresh geography estimate regardless of whether
    // price/rent gets applied below, so restoreHousingEstimateField() can
    // still snap either of them back to it later even on a run that kept
    // the user's own number.
    window.housingLastEstimate[stepNum] = rawFieldMap;
    const fieldMap = priceWasUserEdited
      ? { ...rawFieldMap, [priceLabel]: null }
      : rawFieldMap;
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
        " fields)." +
        (priceWasUserEdited
          ? ` Kept your ${priceLabel === "purchase_price" ? "purchase price" : "monthly rent"}; other fields recalculated.`
          : "") +
        " Review and adjust as needed." +
        (e.note ? " " + e.note : ""),
    );
  } catch (err) {
    showMessage("Error fetching estimate: " + err.message, "error");
  }
}

// A Next Housing Step's "Estimate fields" action (above) re-fetches geography
// defaults for every field. Once a user has hand-typed their own
// purchase_price/monthly_rent, a later re-estimate (e.g. after changing
// city_type or population) should still refresh insurance/utilities/
// maintenance/HOA/mortgage-rate to match the new geography, but must not
// silently overwrite the price/rent number the user chose. Detected by
// comparing the current displayed value against the last-cached estimate
// for that field: if they no longer match, the user changed it since that
// estimate was fetched (or there was no prior estimate to have matched, in
// which case there's nothing to preserve). Pure/no side effects so it's
// unit-testable without the DOM/network work estimateHousingFromState does
// around it.
export function housingPriceWasUserEdited(previousEstimate, priceLabel, currentDisplayValue) {
  if (
    !previousEstimate ||
    !(priceLabel in previousEstimate) ||
    previousEstimate[priceLabel] == null
  ) {
    return false;
  }
  const prevVal = Number(previousEstimate[priceLabel]);
  const curVal = numberFromDisplay(currentDisplayValue);
  if (!(prevVal > 0) || !(curVal > 0)) return false;
  return Math.abs(curVal - prevVal) > 0.5;
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

  // Both purchase and rent: State → Area Type → Population → [Estimate] →
  // remaining fields. Rent used to skip Area Type/Population (silently
  // defaulting to suburban/20,000) -- see design doc §3.4.
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
    "bedrooms",
    "bathrooms",
    "property_type",
    "sqft_band",
    "built_within_years",
  ];
  var RENT_FIRST = ["state", "city_type", "population_size"];
  var RENT_REST = [
    "start_year",
    "end_year",
    "monthly_rent",
    "insurance_annual",
    "utilities_annual",
    "bedrooms",
    "bathrooms",
    "property_type",
    "sqft_band",
    "built_within_years",
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

  // Estimate button: both Purchase and Rent require State, Area Type, and
  // Population -- rent estimates used to silently default to whatever stale
  // city_type/population_size happened to be on those (hidden) rows; both
  // are now surfaced and required for rent too, symmetric with purchase.
  var estimateReady = stateVal && cityTypeVal && popVal;
  var estimateHint = "Enter State, Area Type, and Population to enable";
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
      .map((lbl) => '<button class="btn tiny" type="button" onclick="restoreHousingEstimateField(' + stepNum + ",'" + lbl + '\')">⇺ ' + esc(restoreFieldLabels[lbl]) + "</button>")
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

  html +=
    '<div class="section-note">Not sure what year or location to plan for? The <a href="#" onclick="setStep(\'scenarios\');return false">Optimize next housing move</a> tool (Strategy → Scenario Change Sets) searches candidate sale/purchase years and locations and reuses the same engine as the rest of the plan -- run it, then enter the winning combination into the fields below.</div>';

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
    html += `<div class="scenario-template-card"><div class="scenario-template-card-head"><h4>${esc(t.title)}</h4><p class="small">${esc(t.desc)}</p><button class="btn" type="button" onclick="applyScenarioTemplate('${escJs(t.id)}')">Apply template</button></div>${scenarioDiffTableHtml(scenarioTemplateDiffItems(t), "Template assumptions are already set this way.")}</div>`;
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
    html += `<details class="scenario-set-card"><summary><b>${esc(set.name)}</b><span>${esc(date)} · ${(set.items || []).length} assumption${(set.items || []).length === 1 ? "" : "s"}</span></summary><div class="scenario-set-body">${scenarioDiffTableHtml(diffs, "This saved set matches the current scenario assumptions.")}<div class="table-actions"><button class="btn" type="button" onclick="applySavedScenarioSet('${escJs(set.id)}')">Apply saved set</button>${deleteIconBtn(`deleteSavedScenarioSet('${escJs(set.id)}')`)}</div></div></details>`;
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
  return `<section class="scenario-management"><div class="scenario-management-head"><div><span class="eyebrow">Planning Workbench</span><h3>Scenario Change Sets</h3><p class="small">Templates stage common deterministic what-if overrides. Saved sets are browser-local change sets; review the diff, apply a set, then Save Changes, rebuild, and compare in the Planning Workbench.</p></div><button class="btn primary" type="button" onclick="saveCurrentScenarioSet()">Save current scenario set</button></div><details><summary>Scenario templates</summary>${renderScenarioTemplatesHtml()}</details>${renderHousingOptimizePanelHtml()}<details><summary>Saved named scenario sets</summary>${renderSavedScenarioSetsHtml()}</details><details><summary>Current scenario overrides</summary>${renderCurrentScenarioOverridesHtml(rs)}</details></section>`;
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

// Housing move optimizer (docs/superpowers/specs/2026-09-09-housing-optimization-design.md):
// a search over candidate sale/purchase years and locations, run through the
// existing deterministic engine and Monte Carlo runner via POST
// /api/housing/optimize. Lives next to the scenario templates above and
// reuses this file's diff-table styling for its results table rather than
// introducing new results UI.
const HOUSING_OPT_MAX_LOCATIONS = 4;

export function toggleHousingOptLocationRows() {
  const n = Number(document.getElementById("housingOptLocCount")?.value || 2);
  for (let i = 0; i < HOUSING_OPT_MAX_LOCATIONS; i++) {
    const row = document.getElementById(`housingOptLocRow${i}`);
    if (row) row.hidden = i >= n;
  }
}

export function toggleHousingOptMove2Fields() {
  const el = document.getElementById("housingOptMove2Fields");
  const enabled = !!document.getElementById("housingOptMove2Enabled")?.checked;
  if (el) el.hidden = !enabled;
  if (!enabled) {
    // Move 2 is being disabled -- concurrent mode (and anything it implies)
    // is moot, so reset it rather than silently posting a stale
    // move2_concurrent=true with no move2_window.
    const concurrentCb = document.getElementById("housingOptMove2Concurrent");
    if (concurrentCb) concurrentCb.checked = false;
    const narrowedNote = document.getElementById("housingOptMove2ConcurrentNarrowedNote");
    if (narrowedNote) narrowedNote.hidden = true;
    toggleHousingOptNoDualOwnershipAvailability();
  }
}

export function toggleHousingOptMove2ConcurrentAvailability() {
  const searchMode = String(document.getElementById("housingOptSearchMode")?.value || "full");
  const concurrentCb = document.getElementById("housingOptMove2Concurrent");
  const note = document.getElementById("housingOptMove2ConcurrentNarrowedNote");
  const narrowed = searchMode === "narrowed";
  if (concurrentCb) {
    if (narrowed) concurrentCb.checked = false;
    concurrentCb.disabled = narrowed;
  }
  if (note) note.hidden = !narrowed;
  toggleHousingOptNoDualOwnershipAvailability();
}

// no_dual_ownership does not apply to concurrent mode: concurrent candidates
// always keep both homes, so the checkbox's value is ignored by the backend
// (generate_move2_concurrent_candidates takes no no_dual_ownership argument).
// Disable it and explain why whenever concurrent mode is active, without
// touching its checked state.
export function toggleHousingOptNoDualOwnershipAvailability() {
  const concurrent = !!document.getElementById("housingOptMove2Concurrent")?.checked;
  const noDualCb = document.getElementById("housingOptNoDualOwnership");
  const note = document.getElementById("housingOptNoDualOwnershipConcurrentNote");
  if (noDualCb) noDualCb.disabled = concurrent;
  if (note) note.hidden = !concurrent;
}

function housingOptStateSelectHtml(id, selectedValue) {
  const options = _stateNameChoiceOptions()
    .map(
      (o) =>
        `<option value="${esc(o.value)}"${o.value === selectedValue ? " selected" : ""}>${esc(o.label)}</option>`,
    )
    .join("");
  return `<select id="${id}"><option value="">Select a state</option>${options}</select>`;
}

// Populated from src/housing/zip_screen/data/top_cities.csv, served alongside
// the screen endpoint. Falls back to the free-entry ZIP field when unavailable.
let HOUSING_OPT_TOP_CITIES = [];

function housingOptAnchorCitySelectHtml() {
  const options = HOUSING_OPT_TOP_CITIES.map(
    (c) => `<option value="${esc(c.anchor_zip)}">${esc(c.city)}, ${esc(c.state_abbrev)}</option>`,
  ).join("");
  return `<select id="housingOptAnchorCity"><option value="">Select a city</option>${options}</select>`;
}

export function toggleHousingOptSearchMode() {
  const zip = String(document.getElementById("housingOptGeoMode")?.value || "manual") === "zip_radius";
  const zipFields = document.getElementById("housingOptZipFields");
  const manualFields = document.getElementById("housingOptManualFields");
  if (zipFields) zipFields.hidden = !zip;
  if (manualFields) manualFields.hidden = zip;
}

function housingOptLocationRowHtml(i) {
  return `<div class="housing-opt-location-row" id="housingOptLocRow${i}" ${i >= 2 ? "hidden" : ""}>
    ${housingOptStateSelectHtml(`housingOptLocState${i}`, "")}
    <select id="housingOptLocCity${i}">
      <option value="urban">Urban</option>
      <option value="suburban" selected>Suburban</option>
      <option value="exurban">Exurban</option>
      <option value="rural">Rural</option>
    </select>
    <input type="number" id="housingOptLocPop${i}" value="20000" min="0" style="width:8em" placeholder="Population">
    <select id="housingOptLocBedrooms${i}" title="Bedrooms">
      <option value="2">2BR</option>
      <option value="3" selected>3BR</option>
      <option value="4">4BR</option>
      <option value="5">5+BR</option>
    </select>
    <select id="housingOptLocBathrooms${i}" title="Bathrooms">
      <option value="1">1BA</option>
      <option value="1.5">1.5BA</option>
      <option value="2" selected>2BA</option>
      <option value="2.5">2.5BA</option>
      <option value="3">3BA</option>
      <option value="3.5">3.5+BA</option>
    </select>
    <select id="housingOptLocPropertyType${i}" title="Property type">
      <option value="single_family" selected>Single family</option>
      <option value="townhome">Townhome</option>
      <option value="condo">Condo</option>
      <option value="duplex">Duplex</option>
    </select>
    <select id="housingOptLocSqftBand${i}" title="Square footage">
      <option value="under_1200">Under 1,200 sqft</option>
      <option value="1200_1800">1,200-1,800 sqft</option>
      <option value="1800_2500" selected>1,800-2,500 sqft</option>
      <option value="2500_3500">2,500-3,500 sqft</option>
      <option value="over_3500">Over 3,500 sqft</option>
    </select>
    <input type="number" id="housingOptLocBuiltWithinYears${i}" min="0" style="width:8em" placeholder="Built within N yrs (optional)">
  </div>`;
}

export function renderHousingOptimizePanelHtml() {
  const locationRows = Array.from({ length: HOUSING_OPT_MAX_LOCATIONS }, (_, i) => housingOptLocationRowHtml(i)).join("");
  return `<details class="housing-optimize-panel"><summary>Optimize next housing move</summary><div class="field-list">
    <div class="section-note">Search candidate sale/purchase years and locations for the household's next housing move (optionally a second), reusing the same deterministic engine and Monte Carlo runner as the rest of the plan -- no separate tax model. Results below reuse this page's scenario-diff table styling.</div>
    <label>Location search mode
      <select id="housingOptGeoMode" onchange="toggleHousingOptSearchMode()">
        <option value="manual" selected>Choose locations manually</option>
        <option value="zip_radius">Search by ZIP radius</option>
      </select>
    </label>
    <div id="housingOptZipFields" hidden>
      <div class="subsection-label">Anchor</div>
      <label>City ${housingOptAnchorCitySelectHtml()}</label>
      <label>or ZIP code <input type="text" id="housingOptAnchorZip" maxlength="5" style="width:6em" placeholder="60521"></label>
      <label>Distance from anchor
        <select id="housingOptRadius">
          <option value="5">Within 5 miles</option>
          <option value="10">Within 10 miles</option>
          <option value="25" selected>Within 25 miles</option>
          <option value="50">Within 50 miles</option>
        </select>
      </label>
      <label>Minimum quality score
        <input type="number" id="housingOptMinScore" value="60" min="0" max="100" style="width:6em">
      </label>
      <div class="small">Measures housing and economic stability. Does not measure crime or safety.</div>
      <label>Candidates to send to the optimizer
        <select id="housingOptShortlistSize">
          <option value="2">2</option><option value="3">3</option>
          <option value="4" selected>4</option>
        </select>
      </label>
      <div class="table-actions"><button class="btn" type="button" onclick="previewHousingZipShortlist()">Preview shortlist</button></div>
      <div id="housingOptZipShortlist"></div>
    </div>
    <div id="housingOptManualFields">
      <div class="subsection-label">Candidate locations (2-4)</div>
      <label>Number of candidate locations
        <select id="housingOptLocCount" onchange="toggleHousingOptLocationRows()"><option value="2">2</option><option value="3">3</option><option value="4">4</option></select>
      </label>
      ${locationRows}
    </div>
    <div class="subsection-label">Move 1 search window</div>
    <label>Earliest sale year <input type="number" id="housingOptEarliestSale"></label>
    <label>Latest sale year <input type="number" id="housingOptLatestSale"></label>
    <label>Earliest purchase year <input type="number" id="housingOptEarliestPurchase"></label>
    <label>Latest purchase year <input type="number" id="housingOptLatestPurchase"></label>
    <label>Move 1 action
      <select id="housingOptMove1Action">
        <option value="auto" selected>Auto (search buy &amp; rent)</option>
        <option value="buy">Buy only</option>
        <option value="rent">Rent only</option>
      </select>
    </label>
    <div class="subsection-label"><label><input type="checkbox" id="housingOptMove2Enabled" onchange="toggleHousingOptMove2Fields()"> Consider a second move</label></div>
    <div id="housingOptMove2Fields" hidden>
      <label>Move-2 latest sale year <input type="number" id="housingOptLatestSale2"></label>
      <label>Move-2 latest purchase year <input type="number" id="housingOptLatestPurchase2"></label>
      <label>Anchor count <input type="number" id="housingOptAnchorCount" value="5" min="1" max="10"></label>
      <label>Move 2 action
        <select id="housingOptMove2Action">
          <option value="auto" selected>Auto (search buy &amp; rent)</option>
          <option value="buy">Buy only</option>
          <option value="rent">Rent only</option>
        </select>
      </label>
      <label><input type="checkbox" id="housingOptMove2Concurrent" onchange="toggleHousingOptMove2ConcurrentAvailability(); toggleHousingOptNoDualOwnershipAvailability()"> Concurrent with move 1 (keep move-1 home, add this as a second residence)</label>
      <div id="housingOptMove2ConcurrentNarrowedNote" class="small" hidden>Concurrent mode is only available with Full grid search mode; switch Search mode above to enable it.</div>
    </div>
    <div class="subsection-label">Constraints and objective</div>
    <label><input type="checkbox" id="housingOptNoDualOwnership" checked> Never own two homes at once</label>
    <div id="housingOptNoDualOwnershipConcurrentNote" class="small" hidden>Not applicable in concurrent mode -- both homes are always kept.</div>
    <label>Objective
      <select id="housingOptObjective">
        <option value="net_worth">Ending net worth</option>
        <option value="lifetime_cost">Lifetime housing cost</option>
        <option value="mc_success_rate">Monte Carlo success rate</option>
      </select>
    </label>
    <label>Search mode
      <select id="housingOptSearchMode" onchange="toggleHousingOptMove2ConcurrentAvailability()">
        <option value="full">Full grid (thorough, slower)</option>
        <option value="narrowed">Narrowed search (faster, may miss the best candidate)</option>
      </select>
    </label>
    <label>Move-2 strategy
      <select id="housingOptMove2Strategy">
        <option value="anchored">Anchored on move-1 winners (faster, default)</option>
        <option value="cross_product">Full cross-product (thorough, may be slow or rejected for large windows)</option>
      </select>
    </label>
    <div class="subsection-label">Family presence (optional)</div>
    <label>Region (state) ${housingOptStateSelectHtml("housingOptPresenceRegion", "")}</label>
    <label>From year <input type="number" id="housingOptPresenceStart"></label>
    <label>Through year <input type="number" id="housingOptPresenceEnd"></label>
    <div class="table-actions"><button class="btn primary" type="button" onclick="startHousingOptimization()">Run optimization</button></div>
    <div id="housingOptimizeResults"></div>
  </div></details>`;
}

function housingOptMoveText(move, soldHomeLabel) {
  if (!move) return "";
  const flag = move.sec121_exclusion_lost
    ? ' <span class="small warning">(likely loses §121 exclusion)</span>'
    : "";
  if (move.mode === "concurrent") {
    const action = move.rent_indefinitely
      ? `Also rent in ${esc(move.location.state)} from ${move.start_year}`
      : `Also buy in ${esc(move.location.state)} (${move.start_year})`;
    return `${action} (concurrent with move 1, home 1 kept)${flag}`;
  }
  if (move.rent_indefinitely) {
    return `Sell ${esc(soldHomeLabel)} (${move.sale_year}) then Rent in ${esc(move.location.state)}${flag}`;
  }
  const buyText = `Buy in ${esc(move.location.state)} (${move.purchase_year})`;
  const sellText = `Sell ${esc(soldHomeLabel)} (${move.sale_year})`;
  const overlapNote =
    move.purchase_year < move.sale_year
      ? ` <span class="small">(own both homes ${move.purchase_year}-${move.sale_year})</span>`
      : "";
  const ordered = move.purchase_year < move.sale_year ? [buyText, sellText] : [sellText, buyText];
  return ordered.join(" then ") + overlapNote + flag;
}

function housingOptMovesText(moves) {
  return (moves || [])
    .map((m, idx) => housingOptMoveText(m, idx === 0 ? "original home" : `${moves[0].location.state} home`))
    .join(" then ");
}

const HOUSING_OPT_OBJECTIVE_LABELS = {
  net_worth: "Ending net worth",
  lifetime_cost: "Lifetime housing cost",
  mc_success_rate: "Monte Carlo success rate",
};

function housingOptValueText(row, objective) {
  const v = row && row.objective_value;
  if (v === null || v === undefined) return "—";
  if (objective === "mc_success_rate") return (v * 100).toFixed(1) + "%";
  return "$" + Math.round(v).toLocaleString();
}

function housingOptMcText(row) {
  if (row.mc_success_rate === null || row.mc_success_rate === undefined) return "—";
  return (row.mc_success_rate * 100).toFixed(1) + "%";
}

function housingOptNotesText(row) {
  const notes = [];
  if (row.family_presence_via_rental) notes.push("family presence via rental");
  return notes.join("; ");
}

export function renderHousingZipShortlistHtml(payload) {
  const zs = payload && payload.zip_screen;
  if (!zs) return "";
  const note = `<div class="section-note">${esc(housingZipFunnelText(zs.funnel))}</div>`;
  const disclosure = `<div class="small">${esc(zs.disclosure)}</div>`;
  if (!zs.shortlist || !zs.shortlist.length) {
    const relax = zs.relaxation
      ? `<p class="small">${esc(housingZipRelaxationText(zs.relaxation))}</p>`
      : "";
    return note + relax + disclosure;
  }
  const rows = zs.shortlist.map(housingZipRowHtml).join("");
  const table = `<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr><th>ZIP</th><th>Distance</th><th>Stability score</th><th>Est. price</th></tr></thead><tbody>${rows}</tbody></table>`;
  return note + table + disclosure;
}

function housingZipRowHtml(z) {
  const cross = z.cross_state
    ? ` <span class="small warning">${esc(z.cross_state)} — different state tax treatment</span>`
    : "";
  const upi = z.upi_adjusted
    ? ' <span class="small">(university-adjusted)</span>'
    : "";
  const collapsed = (z.collapsed || []).length
    ? `<div class="small">+${z.collapsed.length} similar nearby: ${z.collapsed.map(esc).join(", ")}</div>`
    : "";
  const coverage = z.coverage_pct < 100
    ? ` <span class="small">(${z.coverage_pct}% data coverage)</span>`
    : "";
  return `<tr><td>${esc(z.zip)} — ${esc(z.city)}, ${esc(z.state)}${cross}${collapsed}</td>
    <td>${z.distance_miles} mi</td>
    <td>${z.nss} <span class="small">${esc(z.band)}</span>${upi}${coverage}</td>
    <td>$${Math.round(z.est_price).toLocaleString()}</td></tr>`;
}

function housingZipFunnelText(f) {
  if (!f) return "";
  return `${f.in_radius} ZIPs in range → ${f.with_data} with data → ${f.above_score} above the score floor → ${f.affordable} affordable → ${f.after_dedup} distinct → ${f.promoted} sent to the optimizer`;
}

function housingZipRelaxationText(r) {
  if (!r) return "";
  return `Lowering the minimum score to ${r.suggested} would return ${r.would_return}.`;
}

export async function previewHousingZipShortlist() {
  const zipSearch = housingOptZipSearchBody();
  if (!zipSearch.anchor.zip) {
    showMessage("Choose an anchor city or enter a ZIP code.", "error");
    return;
  }
  const target = document.getElementById("housingOptZipShortlist");
  try {
    const payload = await api("/api/housing/zip-screen", {
      method: "POST",
      body: JSON.stringify({ zip_search: zipSearch }),
    });
    if (!payload || !payload.success) {
      if (target) target.innerHTML = `<p class="small warning">${esc((payload && payload.error) || "Screen failed.")}</p>`;
      return;
    }
    if (target) target.innerHTML = renderHousingZipShortlistHtml(payload);
  } catch (e) {
    showMessage("Error previewing shortlist: " + e.message, "error");
    if (target) target.innerHTML = "";
  }
}

export function renderHousingOptimizeResultsHtml(payload) {
  if (!payload) return "";
  if (!payload.recommendation) {
    return '<p class="small">No candidates satisfied the search windows and constraints (check no_dual_ownership and family presence).</p>';
  }
  const rec = payload.recommendation;
  const objLabel = HOUSING_OPT_OBJECTIVE_LABELS[payload.objective] || payload.objective;
  const head = `<div class="section-note"><b>Recommended:</b> ${housingOptMovesText(rec.moves)} — ${esc(objLabel)}: ${housingOptValueText(rec, payload.objective)}${housingOptNotesText(rec) ? " · " + esc(housingOptNotesText(rec)) : ""}</div>`;
  const altRows = (payload.alternatives || [])
    .map(
      (row) =>
        `<tr><td>${housingOptMovesText(row.moves).replace(/ then /g, "<br>")}</td><td>${housingOptValueText(row, payload.objective)}</td><td>${housingOptMcText(row)}</td><td>${esc(housingOptNotesText(row))}</td></tr>`,
    )
    .join("");
  const table = altRows
    ? `<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr><th>Alternative</th><th>${esc(objLabel)}</th><th>MC success</th><th>Notes</th></tr></thead><tbody>${altRows}</tbody></table>`
    : '<p class="small">No additional ranked alternatives.</p>';
  return head + table;
}

export async function runHousingOptimization() {
  // In ZIP mode, POST body.zip_search (never body.locations) built by
  // housingOptZipSearchBody(): { anchor, radius_miles, min_quality_score,
  // shortlist_size, property_spec }. Manual mode sends body.locations
  // instead -- the server rejects a request carrying both.
  const geoMode = String(document.getElementById("housingOptGeoMode")?.value || "manual");
  const body = {};
  if (geoMode === "zip_radius") {
    body.zip_search = housingOptZipSearchBody();
    if (!body.zip_search.anchor.zip) {
      showMessage("Choose an anchor city or enter a ZIP code.", "error");
      return;
    }
  } else {
    const numLocs = Number(document.getElementById("housingOptLocCount")?.value || 2);
    const locations = [];
    for (let i = 0; i < numLocs; i++) {
      const state = String(document.getElementById(`housingOptLocState${i}`)?.value || "").trim();
      if (!state) {
        showMessage(`Enter a state for candidate location ${i + 1}.`, "error");
        return;
      }
      const builtWithinYearsRaw = document.getElementById(`housingOptLocBuiltWithinYears${i}`)?.value;
      locations.push({
        state,
        city_type: String(document.getElementById(`housingOptLocCity${i}`)?.value || "suburban"),
        population_size: Number(document.getElementById(`housingOptLocPop${i}`)?.value || 20000),
        bedrooms: Number(document.getElementById(`housingOptLocBedrooms${i}`)?.value || 3),
        bathrooms: Number(document.getElementById(`housingOptLocBathrooms${i}`)?.value || 2),
        property_type: String(document.getElementById(`housingOptLocPropertyType${i}`)?.value || "single_family"),
        sqft_band: String(document.getElementById(`housingOptLocSqftBand${i}`)?.value || "1800_2500"),
        built_within_years: builtWithinYearsRaw ? Number(builtWithinYearsRaw) : null,
      });
    }
    body.locations = locations;
  }
  Object.assign(body, {
    move1_window: {
      earliest_sale_year: Number(document.getElementById("housingOptEarliestSale")?.value || 0),
      latest_sale_year: Number(document.getElementById("housingOptLatestSale")?.value || 0),
      earliest_purchase_year: Number(document.getElementById("housingOptEarliestPurchase")?.value || 0),
      latest_purchase_year: Number(document.getElementById("housingOptLatestPurchase")?.value || 0),
    },
    anchor_count: Number(document.getElementById("housingOptAnchorCount")?.value || 5),
    no_dual_ownership: !!document.getElementById("housingOptNoDualOwnership")?.checked,
    objective: String(document.getElementById("housingOptObjective")?.value || "net_worth"),
    search_mode: String(document.getElementById("housingOptSearchMode")?.value || "full"),
    move2_strategy: String(document.getElementById("housingOptMove2Strategy")?.value || "anchored"),
    move1_action: String(document.getElementById("housingOptMove1Action")?.value || "auto"),
    move2_action: String(document.getElementById("housingOptMove2Action")?.value || "auto"),
    move2_concurrent: !!document.getElementById("housingOptMove2Concurrent")?.checked,
  });
  if (document.getElementById("housingOptMove2Enabled")?.checked) {
    body.move2_window = {
      latest_sale_year_2: Number(document.getElementById("housingOptLatestSale2")?.value || 0),
      latest_purchase_year_2: Number(document.getElementById("housingOptLatestPurchase2")?.value || 0),
    };
  }
  const region = String(document.getElementById("housingOptPresenceRegion")?.value || "").trim();
  if (region) {
    body.family_presence = {
      region,
      start_year: Number(document.getElementById("housingOptPresenceStart")?.value || 0),
      end_year: Number(document.getElementById("housingOptPresenceEnd")?.value || 0),
    };
  }
  const resultsEl = document.getElementById("housingOptimizeResults");
  if (resultsEl) resultsEl.innerHTML = "";
  setBuildOverlay(
    true,
    "Optimizing next housing move",
    "Searching candidate sale/purchase years and locations against the plan engine. This can take a little while…",
    "waiting",
  );
  try {
    const resp = await api("/api/housing/optimize", { method: "POST", body: JSON.stringify(body) });
    if (resp && resp.success) {
      if (resultsEl) {
        resultsEl.innerHTML =
          renderHousingZipShortlistHtml(resp) + renderHousingOptimizeResultsHtml(resp);
      }
    } else {
      showMessage("Optimization error: " + (resp && resp.error ? resp.error : "unknown error"), "error");
      if (resultsEl) resultsEl.innerHTML = "";
    }
  } catch (e) {
    showMessage("Error running housing optimization: " + e.message, "error");
    if (resultsEl) resultsEl.innerHTML = "";
  } finally {
    hideBuildOverlay();
  }
}

function housingOptZipSearchBody() {
  const anchorZip =
    String(document.getElementById("housingOptAnchorZip")?.value || "").trim() ||
    String(document.getElementById("housingOptAnchorCity")?.value || "").trim();
  return {
    anchor: { zip: anchorZip },
    radius_miles: Number(document.getElementById("housingOptRadius")?.value || 25),
    min_quality_score: Number(document.getElementById("housingOptMinScore")?.value || 60),
    shortlist_size: Number(document.getElementById("housingOptShortlistSize")?.value || 4),
    property_spec: {
      bedrooms: Number(document.getElementById("housingOptLocBedrooms0")?.value || 3),
      bathrooms: Number(document.getElementById("housingOptLocBathrooms0")?.value || 2),
      property_type: String(document.getElementById("housingOptLocPropertyType0")?.value || "single_family"),
      sqft_band: String(document.getElementById("housingOptLocSqftBand0")?.value || "1800_2500"),
      built_within_years: Number(document.getElementById("housingOptLocBuiltWithinYears0")?.value) || null,
    },
  };
}

// Thin alias for the panel's "Run optimization" button (present since the
// original housing optimizer, commit fe496e4, predating ZIP-radius search).
// Keeping it distinct from `runHousingOptimization` itself only avoids the
// button's onclick text shadowing that function's definition for tooling
// that scans this file's source; behavior is identical.
export function startHousingOptimization() {
  return runHousingOptimization();
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
  toggleHousingOptSearchMode,
  toggleHousingOptLocationRows,
  toggleHousingOptMove2Fields,
  toggleHousingOptMove2ConcurrentAvailability,
  toggleHousingOptNoDualOwnershipAvailability,
  renderHousingOptimizePanelHtml,
  renderHousingOptimizeResultsHtml,
  renderHousingZipShortlistHtml,
  previewHousingZipShortlist,
  runHousingOptimization,
  startHousingOptimization,
  seedHousingRows,
});
