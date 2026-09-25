/* Spending Adjustments table (#335, spec §5) -- the Adjustments accordion
   at the end of Spending Model, hosted by renderDomainBudgetTable() in
   dashboard_decomp_spending_taxonomy.js.

   Each row is a one-time step applied multiplicatively from its start year
   through its end year (blank = plan end); rows on the same category
   compound in start-year order, and an "All <tracking type>" row compounds
   with a category's own rows. The engine side is src/spending_adjustments.py;
   rows persist as Cashflow / Spending Adjustments adj_N_* rows through
   /api/spending-adjustments, saved with the rest of the plan by
   saveWorkingCopy(). State lives in this module, not dashboard.js. */

export const ADJUSTABLE_TRACKING_TYPES = [
  "Core Expenses",
  "Housing",
  "Wellness",
  "Travel",
];
const ALL_PREFIX = "ALL:";

let spendingAdjustments = [];
let spendingAdjustmentsLoaded = false;
let spendingAdjustmentsLoading = false;
let spendingAdjustmentsChanged = false;

// Same semantics as src/spending_adjustments.py adjustment_factor().
export function adjustmentFactor(adjs, categoryId, trackingType, year) {
  const applies = (a) =>
    String(a.category || "").startsWith(ALL_PREFIX)
      ? a.category.slice(ALL_PREFIX.length) === trackingType
      : a.category === categoryId;
  let factor = 1;
  (adjs || [])
    .filter(applies)
    .map((a) => ({
      start: parseInt(a.start_year, 10),
      end: parseInt(a.end_year, 10) || null,
      pct: Number(String(a.change_pct || "").replace("%", "")),
    }))
    .filter((a) => a.start && Number.isFinite(a.pct))
    .sort((a, b) => a.start - b.start)
    .forEach((a) => {
      if (a.start <= year && (a.end === null || year <= a.end))
        factor *= 1 + a.pct / 100;
    });
  return factor;
}

// Every active category in Core / Housing / Wellness / Travel plus one
// "All <tracking type>" option per type; never Large Discretionary, Taxes or
// Business.
export function spendingAdjustmentCategoryOptions(flat) {
  const out = [];
  ADJUSTABLE_TRACKING_TYPES.forEach((tt) => {
    out.push({ value: ALL_PREFIX + tt, label: `All ${tt}`, trackingType: tt });
    Object.values(flat || {})
      .filter((c) => c.tracking_type === tt && (c.status || "active") === "active")
      .sort((a, b) => String(a.label).localeCompare(String(b.label)))
      .forEach((c) =>
        out.push({ value: c.id, label: c.label || c.id, trackingType: tt }),
      );
  });
  return out;
}

function trackingTypeFor(category, flat) {
  if (String(category || "").startsWith(ALL_PREFIX))
    return category.slice(ALL_PREFIX.length);
  return ((flat || {})[category] || {}).tracking_type || "";
}

// Helper text for row i: the compounded level from its start year, e.g.
// "72% of today's level from 2042".
export function spendingAdjustmentResultText(adjs, i, flat) {
  const row = (adjs || [])[i] || {};
  const start = parseInt(row.start_year, 10);
  if (!row.category || !start) return "";
  const tt = trackingTypeFor(row.category, flat);
  const cid = row.category.startsWith(ALL_PREFIX) ? "" : row.category;
  const pct = Math.round(adjustmentFactor(adjs, cid, tt, start) * 1000) / 10;
  const end = parseInt(row.end_year, 10);
  const then = end
    ? `; back to ${Math.round(adjustmentFactor(adjs, cid, tt, end + 1) * 1000) / 10}% after ${end}`
    : "";
  return `${pct}% of today's level from ${start}${then}`;
}

export function spendingAdjustmentsDirty() {
  return spendingAdjustmentsChanged;
}

export function resetSpendingAdjustments() {
  spendingAdjustments = [];
  spendingAdjustmentsLoaded = false;
  spendingAdjustmentsChanged = false;
}

export async function loadSpendingAdjustments() {
  if (spendingAdjustmentsLoading) return;
  spendingAdjustmentsLoading = true;
  try {
    const out = await api("/api/spending-adjustments");
    spendingAdjustments = (out && out.adjustments) || [];
    spendingAdjustmentsChanged = false;
  } catch (e) {
    spendingAdjustments = [];
  }
  spendingAdjustmentsLoaded = true;
  spendingAdjustmentsLoading = false;
  renderMain();
}

export async function saveSpendingAdjustments(sync = false) {
  if (!spendingAdjustmentsChanged) return { updated: 0 };
  const out = await api("/api/spending-adjustments", {
    method: "POST",
    body: JSON.stringify({ adjustments: spendingAdjustments, sync }),
  });
  spendingAdjustmentsChanged = false;
  return out;
}

function markSpendingAdjustmentsDirty() {
  noteSpecialSessionChange("Spending adjustments table");
  spendingAdjustmentsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}

function refreshSpendingAdjustmentResults() {
  if (typeof document === "undefined" || !document.querySelectorAll) return;
  document.querySelectorAll("[data-adj-result]").forEach((el) => {
    const i = Number(el.getAttribute("data-adj-result"));
    el.textContent = spendingAdjustmentResultText(spendingAdjustments, i, taxonomyFlat);
  });
}

export function addSpendingAdjustment() {
  spendingAdjustments.push({
    category: ALL_PREFIX + ADJUSTABLE_TRACKING_TYPES[0],
    start_year: String(new Date().getFullYear() + 1),
    end_year: "",
    change_pct: "",
  });
  markSpendingAdjustmentsDirty();
  renderMain();
}

export function updateSpendingAdjustment(i, field, val) {
  if (!spendingAdjustments[i]) return;
  spendingAdjustments[i][field] = String(val == null ? "" : val).trim();
  markSpendingAdjustmentsDirty();
  refreshSpendingAdjustmentResults();
}

export async function deleteSpendingAdjustment(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Spending Adjustment",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  spendingAdjustments.splice(i, 1);
  markSpendingAdjustmentsDirty();
  renderMain();
}

export function renderSpendingAdjustmentsTable() {
  if (!spendingAdjustmentsLoaded) setTimeout(() => loadSpendingAdjustments(), 0);
  if (!taxonomyData && typeof loadTaxonomy === "function")
    setTimeout(() => loadTaxonomy(false), 0);
  const flat = taxonomyFlat || {};
  const options = spendingAdjustmentCategoryOptions(flat);
  let html =
    '<div class="section-note">A step change to a category (or a whole tracking type) from a start year; inflation continues on the stepped amount. Rows on the same category compound in start-year order, and an "All" row compounds with a category\'s own rows. Leave End year blank to run through plan end. Large Discretionary, Taxes and Business are not adjustable.</div>';
  html +=
    '<div class="table-actions"><button class="btn" type="button" onclick="addSpendingAdjustment()">Add Adjustment</button></div>';
  html +=
    '<div class="lot-table-wrap"><table class="lot-table spending-adjustments-table"><thead><tr><th>Category</th><th>Start year</th><th>End year</th><th>Change %</th><th>Result</th><th>Actions</th></tr></thead><tbody>';
  if (!spendingAdjustments.length)
    html +=
      '<tr><td colspan="6" class="small" style="padding:12px">No adjustments. Add one to step a category down (or up) from a given year.</td></tr>';
  spendingAdjustments.forEach((a, i) => {
    const cur = a.category || "";
    const known = options.some((o) => o.value === cur);
    const groups = ADJUSTABLE_TRACKING_TYPES.map(
      (tt) =>
        `<optgroup label="${esc(tt)}">${options
          .filter((o) => o.trackingType === tt)
          .map((o) => `<option value="${esc(o.value)}"${o.value === cur ? " selected" : ""}>${esc(o.label)}</option>`)
          .join("")}</optgroup>`,
    ).join("");
    const stale = cur && !known ? `<option value="${esc(cur)}" selected>${esc(cur)}</option>` : "";
    html += `<tr data-adj-row="${i}"><td><select onchange="updateSpendingAdjustment(${i},'category',this.value)">${stale}${groups}</select></td><td><input type="number" value="${esc(a.start_year || "")}" placeholder="YYYY" oninput="updateSpendingAdjustment(${i},'start_year',this.value)" style="width:90px"></td><td><input type="number" value="${esc(a.end_year || "")}" placeholder="plan end" oninput="updateSpendingAdjustment(${i},'end_year',this.value)" style="width:90px"></td><td><input type="text" value="${esc(a.change_pct || "")}" placeholder="-20" oninput="updateSpendingAdjustment(${i},'change_pct',this.value)" style="width:70px"></td><td class="small" data-adj-result="${i}">${esc(spendingAdjustmentResultText(spendingAdjustments, i, flat))}</td><td>${deleteIconBtn(`deleteSpendingAdjustment(${i})`)}</td></tr>`;
  });
  return html + "</tbody></table></div>";
}

// The Adjustments accordion, after the Tracking Type accordions.
export function renderSpendingAdjustmentsAccordion() {
  return `<details class="taxonomy-type-section spending-adjustments" data-dkey="budget:core:adjustments"><summary><b>Adjustments</b> <span class="small">${spendingAdjustments.length} step change${spendingAdjustments.length === 1 ? "" : "s"}</span></summary>${renderSpendingAdjustmentsTable()}</details>`;
}

// Every export above is also re-attached to window: saveWorkingCopy() and
// hasUnsavedPlanChanges() reach the save/dirty hooks through window, and
// this file's rendered HTML uses inline onclick/onchange handlers.
Object.assign(window, {
  ADJUSTABLE_TRACKING_TYPES,
  adjustmentFactor,
  spendingAdjustmentCategoryOptions,
  spendingAdjustmentResultText,
  spendingAdjustmentsDirty,
  resetSpendingAdjustments,
  loadSpendingAdjustments,
  saveSpendingAdjustments,
  addSpendingAdjustment,
  updateSpendingAdjustment,
  deleteSpendingAdjustment,
  renderSpendingAdjustmentsTable,
  renderSpendingAdjustmentsAccordion,
});
Object.defineProperty(window, "spendingAdjustments", {
  get: () => spendingAdjustments,
  set: (v) => {
    spendingAdjustments = v;
  },
  configurable: true,
});
