/* Spending Model source field groups (#338 W-C, task C2).

   Spending Model is the single read/write surface for every spending
   Tracking Type: one accordion per type, in TRACKING_TYPE_ORDER. Housing,
   Wellness and Travel used to be "read-only reference -- budgeted on its
   source page" there, with their editable inputs on standalone Housing /
   Wellness / Travel pages. The non-budget field groups those pages rendered
   now live here, extracted rather than copied (the W13
   familyBusinessGroupsHtml() precedent), and renderDomainBudgetTable() calls
   them from inside each accordion body.

   Only Housing COSTS render in the Housing accordion. Home value / mortgage
   balance and home sale / next moves / state over time are housing plan
   inputs, not spending; they stay in housingPlanSectionsHtml()
   (dashboard_decomp_housing_scenarios.js), shown in a collapsed section
   under the Housing accordion until W-E moves them to Other Assets and
   Next Housing Move.

   Everything this module calls (fieldHtml, norm, esc, rowsForStep,
   rowIsRetirementWellness, housingPlanSectionsHtml, searchText) resolves
   through the window bridge at call time, so it has no load-order
   dependency on dashboard.js. */

// Planning order for the Spending Model accordions (§3 of
// docs/superpowers/specs/2026-09-24-taxonomy-and-spending-restructure-design.md).
// Deliberately NOT src/spending_tracker.py's TRACKING_TYPE_ORDER: that one
// orders reports and CSV output and puts Wellness/Housing last; this one is
// the order a planner fills the model in.
export const TRACKING_TYPE_ORDER = [
  "Core Expenses",
  "Housing",
  "Wellness",
  "Travel",
  "Large Discretionary",
  "Taxes",
  "Business",
];

export function sortByTrackingTypeOrder(types) {
  const rank = (t) => {
    const i = TRACKING_TYPE_ORDER.indexOf(t.tracking_type);
    return i < 0 ? TRACKING_TYPE_ORDER.length : i;
  };
  return (types || [])
    .map((t, i) => [t, i])
    .sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1])
    .map((p) => p[0]);
}

// Real-estate taxes, insurance, maintenance, utilities and HOA are budget
// categories (Housing Budget Detail); the mortgage balance is a liability
// and moves to Other Assets and Liabilities in W-E. Location descriptors
// (city_type/population_size) feed the housing estimator, not spending.
const HOUSING_MORTGAGE_NON_COST = [
  "annual_real_estate_taxes",
  "balance_as_of_plan_start",
];
const HOUSING_CURRENT_HOME_NON_COST = [
  "city_type",
  "population_size",
  "hoa_pct",
  "hoa_annual",
  "homeowners_insurance_annual",
  "home_maintenance_annual",
  "utilities_annual",
];

export function rowIsHousingCost(r) {
  const sec = String((r && r.section) || "").trim();
  const sub = norm((r && r.subsection) || "");
  const lbl = norm((r && r.label) || "");
  if (sec === "Cashflow" && sub === "mortgage")
    return !HOUSING_MORTGAGE_NON_COST.includes(lbl);
  if (sec === "Housing" && sub === "current_home")
    return !HOUSING_CURRENT_HOME_NON_COST.includes(lbl);
  return false;
}

// Rows the Spending Model now owns on behalf of the retired Housing and
// Wellness steps -- rawRowsForStep("spending_core") includes them, so
// sourceStepForRow() and every "jump to source field" link land on
// Spending Model.
export function rowIsSpendingSourceRow(r) {
  return rowIsHousingCost(r) || rowIsRetirementWellness(r);
}

export function housingCostGroupsHtml(rows) {
  const cost = (rows || []).filter(rowIsHousingCost);
  let html =
    '<div class="section-note">Housing costs: mortgage payment timing and other recurring home costs. Real-estate taxes, homeowners insurance, maintenance, utilities, and HOA are budgeted in the groups below. Click <button class="btn btn-sm" type="button" onclick="seedHousingRows()">Seed Housing Fields</button> to add any missing housing fields.</div>';
  if (cost.length)
    html += '<div class="field-list">' + cost.map(fieldHtml).join("") + "</div>";
  return html;
}

export function wellnessGroupsHtml(rows) {
  let html =
    '<div class="section-note"><b>Wellness is the authoritative view for healthcare spending.</b> Enter Pre-65 premiums, Medicare Part B/D/G premiums, and non-premium medical, dental, vision, Rx/OTC, and out-of-pocket estimates. The projection uses these values as-entered for cash flow and income impact; Medicare premium categories are split to match spending taxonomy.</div>';
  // The old Wellness page showed its own rows only while searching; the
  // budget groups below are the everyday editor.
  const own = (rows || []).filter(rowIsRetirementWellness);
  if (searchText.trim() && own.length)
    html += '<div class="field-list">' + own.map(fieldHtml).join("") + "</div>";
  return html;
}

export function travelGroupsHtml() {
  return `<div class="section-note">${esc(domainBudgetNote("travel"))} A group in Summary mode budgets the whole group -- group number wins over its categories.</div>`;
}

// Body prefix for a Tracking Type's Spending Model accordion, before its
// budget groups; "" for types with no source field groups.
export function spendingSourceHeadHtml(tt) {
  if (tt === "Housing")
    return housingCostGroupsHtml(rowsForStep("spending_mortgage_events"));
  if (tt === "Wellness")
    return wellnessGroupsHtml(rowsForStep("retirement_wellness"));
  if (tt === "Travel") return travelGroupsHtml();
  if (tt === "Large Discretionary") return renderLargeDiscretionaryBudgetPage();
  return "";
}

// Body suffix, after the budget groups: the housing plan inputs that are
// not spending but have no other home until W-E.
export function spendingSourceTailHtml(tt) {
  if (tt !== "Housing") return "";
  return `<details class="taxonomy-type-subsection" data-dkey="housing:plan"><summary class="section-header">Home value, sale &amp; next moves</summary><div class="section-body">${housingPlanSectionsHtml(rowsForStep("spending_mortgage_events"))}</div></details>`;
}

export function domainBudgetNote(domain) {
  if (domain === "core")
    return "Spending Categories is comprehensive: Income and every expense Tracking Type, including Taxes, should appear in the hierarchy -- only internal transfers are excluded. Housing, Wellness, and Travel are edited in their own accordions below. Each group header shows both Annual Budget (what you entered) and Projection (the value the projection engine actually uses as the starting spend amount). They are usually equal — expand the help below to see when and why they can differ.";
  if (domain === "housing")
    return "Housing is the only editable place for mortgage/rent, homeowners insurance, home maintenance, utilities, real-estate taxes, and home improvement projects.";
  if (domain === "healthcare")
    return "Wellness is the only editable place for the Healthcare Premium group (Pre-65 Healthcare Premium plus Medicare Part B, Part D, and Part G), medical, dental, vision, drugs Rx/OTC, vitamins/supplements, and the medical OOP cap/reference.";
  if (domain === "travel")
    return "Travel is the only editable place for recurring travel projection inputs plus transaction-based travel detail. Domestic-travel and lifestyle labels are intentionally not used here.";
  return "Large Discretionary rows are one-time: Weddings, Large Gifts, Education (not 529-funded), Auto, or Other -- one amount in one year, never annualized.";
}

// Every export above is also re-attached to window: dashboard.js and the
// other leaf modules call these as bare globals.
Object.assign(window, {
  TRACKING_TYPE_ORDER,
  sortByTrackingTypeOrder,
  rowIsHousingCost,
  rowIsSpendingSourceRow,
  housingCostGroupsHtml,
  wellnessGroupsHtml,
  travelGroupsHtml,
  spendingSourceHeadHtml,
  spendingSourceTailHtml,
  domainBudgetNote,
});
