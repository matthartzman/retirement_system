// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.
//
// #336 (spec §4): Large Discretionary is one section -- the Large
// Discretionary accordion in Spending Model -- and one-time only. Each row is
// one amount in one year; it is never annualized. Mirrors
// src/large_discretionary.py (LD_CATEGORIES / LD_CATEGORY_IDS).

export const LARGE_DISC_TYPES = [
  "Weddings",
  "Large Gifts",
  "Education",
  "Auto",
  "Other",
];

const LARGE_DISC_TYPE_LABELS = { Education: "Education (not 529-funded)" };

const LARGE_DISC_TYPE_CATEGORY = {
  Weddings: "weddings",
  "Large Gifts": "significant_gifts",
  Education: "ld_education",
  Auto: "ld_auto",
  Other: "other_large_discretionary",
};

// children_weddings is a retired id kept so its legacy lines still render.
export const LARGE_DISC_CATEGORY_IDS = [
  ...Object.values(LARGE_DISC_TYPE_CATEGORY),
  "children_weddings",
];

// A legacy repeatable row expanding to more than this many one-time rows is
// really recurring spending (same threshold as the backend migration).
const LARGE_DISC_CORE_THRESHOLD = 10;

export function largeDiscTypeLabel(type) {
  return LARGE_DISC_TYPE_LABELS[type] || type;
}

export function updateLargeDiscLineMoney(lineId, field, el) {
  updateLargeDiscLine(lineId, field, String(budgetMoneyNumber(el && el.value)));
}

export function renderTravelBudgetPage() {
  return renderDomainBudgetPage("travel");
}

export function largeDiscTypeFromLine(line) {
  const cid = String(line.category_id || "").toLowerCase();
  const label = String(line.label || "").toLowerCase();
  for (const [type, id] of Object.entries(LARGE_DISC_TYPE_CATEGORY)) {
    if (cid === id) return type;
  }
  if (cid === "children_weddings" || label.includes("wedding"))
    return "Weddings";
  if (label.includes("gift")) return "Large Gifts";
  if (label.includes("education") || label.includes("tuition"))
    return "Education";
  if (label.includes("vehicle") || label.includes("auto")) return "Auto";
  return "Other";
}

export function largeDiscCategoryFromType(type) {
  return LARGE_DISC_TYPE_CATEGORY[type] || LARGE_DISC_TYPE_CATEGORY.Other;
}

export function updateLargeDiscLine(lineId, field, val) {
  const l = (budgetLines || []).find((x) => x.line_id === lineId);
  if (!l) return;
  if (field === "type") {
    l.category_id = largeDiscCategoryFromType(val);
    l.label = val;
  } else {
    l[field] = val;
  }
  markBudgetLinesDirty();
}

export function addLargeDiscLine() {
  budgetLines.push({
    section: "large_discretionary",
    line_id: "ld_" + (Date.now() % 1000000),
    label: "Other",
    category_id: "other_large_discretionary",
    start_year: "",
    end_year: "",
    one_time_year: String(new Date().getFullYear()),
    amount_per_year: "",
    mode: "detail",
    notes: "",
  });
  markBudgetLinesDirty();
  renderMain();
}

export async function deleteLargeDiscLine(lineId) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Large Discretionary row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  budgetLines = (budgetLines || []).filter((l) => l.line_id !== lineId);
  markBudgetLinesDirty();
  renderMain();
}

export function isLargeDiscLine(l) {
  return (
    String(l.section || "") === "large_discretionary" ||
    LARGE_DISC_CATEGORY_IDS.includes(String(l.category_id || ""))
  );
}

// Legacy repeatable rows (start/end year, annual amount) become one dated row
// per year. Returns the import notices; mutates `lines` in place.
export function migrateLargeDiscLines(lines, planEnd) {
  const notices = [];
  for (let i = lines.length - 1; i >= 0; i--) {
    const l = lines[i];
    if (!isLargeDiscLine(l) || String(l.one_time_year || "").trim()) continue;
    const start = parseInt(l.start_year, 10) || 0;
    const end = parseInt(l.end_year, 10) || planEnd || start;
    if (!start) continue;
    const years = [];
    for (let y = start; y <= Math.max(start, end); y++) years.push(y);
    lines.splice(
      i,
      1,
      ...years.map((y) => ({
        ...l,
        line_id: `${l.line_id}_${y}`,
        start_year: "",
        end_year: "",
        one_time_year: String(y),
      })),
    );
    let notice = `"${l.label || largeDiscTypeFromLine(l)}" (${start}-${Math.max(start, end)}) was converted to ${years.length} one-time rows.`;
    if (years.length > LARGE_DISC_CORE_THRESHOLD)
      notice += " It repeats for more than 10 years; consider moving it to a Core category.";
    notices.push(notice);
  }
  return notices.reverse();
}

function largeDiscPlanEnd() {
  const raw =
    typeof rowConfigValue === "function"
      ? rowConfigValue("plan_end_year", rowConfigValue("plan_end", ""))
      : "";
  return Number(String(raw || "").replace(/[^0-9]/g, "")) || 0;
}

function largeDisc529On() {
  return (
    typeof optionalFunctionEnabled === "function" &&
    optionalFunctionEnabled("education_funding_529")
  );
}

export function renderLargeDiscretionaryBudgetPage() {
  if (!budgetLinesLoaded) {
    setTimeout(() => loadBudgetLines(false), 0);
  }
  const notices = migrateLargeDiscLines(budgetLines || [], largeDiscPlanEnd());
  if (notices.length) markBudgetLinesDirty();
  const lines = (budgetLines || []).filter(isLargeDiscLine);
  const thisYear = new Date().getFullYear();
  let budgetThisYear = 0;
  lines.forEach((l) => {
    const amt =
      Number(String(l.amount_per_year || "").replace(/[$,]/g, "")) || 0;
    if (parseInt(l.one_time_year, 10) === thisYear) budgetThisYear += amt;
  });
  let html = '<div class="holdings large-disc-section">';
  if (notices.length)
    html += `<div class="section-note large-disc-import-notice"><b>Imported repeatable rows as one-time rows:</b><ul>${notices.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>Save to keep the conversion.</div>`;
  if (largeDisc529On())
    html +=
      '<div class="section-note large-disc-529-caution">529 education funding is on: enter only education costs the 529 does not pay here, so they are not counted twice.</div>';
  html +=
    '<div class="table-actions"><button class="btn primary" ' +
    (budgetLinesChanged ? "" : "disabled") +
    ' onclick="saveAll(true)">Save Changes</button><button class="btn" onclick="loadBudgetLines(true)">Reload</button><button class="btn" onclick="addLargeDiscLine()">Add Row</button></div>';
  html +=
    '<div class="lot-table-wrap"><table class="lot-table large-disc-table"><thead><tr><th>Category</th><th>Amount</th><th>Year</th><th>Note</th><th>In budget</th><th>Actions</th></tr></thead><tbody>';
  if (!lines.length) {
    html +=
      '<tr><td colspan="6" class="small" style="padding:12px">No Large Discretionary rows. Add one row per one-time expense.</td></tr>';
  }
  lines.forEach(function (l) {
    const lid = esc(l.line_id);
    const typ = largeDiscTypeFromLine(l);
    const inBudget = parseInt(l.one_time_year, 10) === thisYear;
    html += `<tr><td><select onchange="updateLargeDiscLine('${lid}','type',this.value)">${LARGE_DISC_TYPES.map((t) => `<option value="${esc(t)}" ${t === typ ? "selected" : ""}>${esc(largeDiscTypeLabel(t))}</option>`).join("")}</select></td><td><input type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(l.amount_per_year))}" onfocus="focusBudgetMoney(this)" oninput="updateLargeDiscLineMoney('${lid}','amount_per_year',this)" onblur="blurBudgetMoney(this)" style="width:110px"></td><td><input type="number" value="${esc(l.one_time_year || "")}" oninput="updateLargeDiscLine('${lid}','one_time_year',this.value)" style="width:90px"></td><td><input value="${esc(l.notes || "")}" placeholder="Optional" oninput="updateLargeDiscLine('${lid}','notes',this.value)" style="width:200px"></td><td class="large-disc-in-budget" title="Counts toward this year's budget only when its year is ${thisYear}">${inBudget ? "✓" : "—"}</td><td>${deleteIconBtn(`deleteLargeDiscLine('${lid}')`)}</td></tr>`;
  });
  html += `</tbody></table></div><div class="section-note"><b>This year's budget: $${Math.round(budgetThisYear).toLocaleString()}</b> (rows dated ${thisYear}). Each row is one-time: it projects only in its own year and is never annualized.</div></div>`;
  return html;
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  LARGE_DISC_TYPES,
  LARGE_DISC_CATEGORY_IDS,
  largeDiscTypeLabel,
  updateLargeDiscLineMoney,
  renderTravelBudgetPage,
  largeDiscTypeFromLine,
  largeDiscCategoryFromType,
  updateLargeDiscLine,
  addLargeDiscLine,
  deleteLargeDiscLine,
  isLargeDiscLine,
  migrateLargeDiscLines,
  renderLargeDiscretionaryBudgetPage,
});
