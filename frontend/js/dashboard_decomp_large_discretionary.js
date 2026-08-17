// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function updateLargeDiscLineMoney(lineId, field, el) {
  updateLargeDiscLine(lineId, field, String(budgetMoneyNumber(el && el.value)));
}

export function renderTravelBudgetPage() {
  return renderDomainBudgetPage("travel");
}

export function largeDiscTypeFromLine(line) {
  const cid = String(line.category_id || "").toLowerCase();
  const label = String(line.label || "").toLowerCase();
  if (
    cid === "weddings" ||
    cid === "children_weddings" ||
    label.includes("wedding")
  )
    return "Wedding";
  if (
    cid === "significant_gifts" ||
    cid === "large_gifts" ||
    label.includes("gift")
  )
    return "Large Gifts";
  return "Other";
}

export function largeDiscCategoryFromType(type) {
  if (type === "Wedding") return "weddings";
  if (type === "Large Gifts") return "significant_gifts";
  return "other_large_discretionary";
}

export function updateLargeDiscLine(lineId, field, val) {
  const l = (budgetLines || []).find((x) => x.line_id === lineId);
  if (!l) return;
  if (field === "type") {
    l.category_id = largeDiscCategoryFromType(val);
    if (!String(l.label || "").trim()) l.label = val;
  } else {
    l[field] = val;
  }
  markBudgetLinesDirty();
}

export function addLargeDiscLine() {
  budgetLines.push({
    section: "large_discretionary",
    line_id: "ld_" + (Date.now() % 1000000),
    label: "",
    category_id: "other_large_discretionary",
    start_year: "",
    end_year: "",
    one_time_year: "",
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
      title: "Delete Budget Detail",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  budgetLines = (budgetLines || []).filter((l) => l.line_id !== lineId);
  markBudgetLinesDirty();
  renderMain();
}

export function renderLargeDiscretionaryBudgetPage() {
  if (!budgetLinesLoaded) {
    setTimeout(() => loadBudgetLines(false), 0);
  }
  const lines = (budgetLines || []).filter(
    (l) =>
      String(l.section || "") === "large_discretionary" ||
      LARGE_DISC_CATEGORY_IDS.includes(String(l.category_id || "")),
  );
  // #208: Large Discretionary rows are inherently lumpy (weddings, gifts, one-time
  // purchases) -- summing one-time and recurring rows into a single "$X/yr" figure
  // implied an ongoing annual commitment that doesn't exist. Split the total so a
  // one-time lump is shown as a lump, not folded into a misleading per-year rate.
  let oneTimeTotal = 0;
  let recurringTotal = 0;
  lines.forEach((l) => {
    const amt = Number(String(l.amount_per_year || "").replace(/[$,]/g, "")) || 0;
    if (l.one_time_year) oneTimeTotal += amt;
    else recurringTotal += amt;
  });
  let html =
    '<div class="holdings"><div class="table-actions"><button class="btn primary" ' +
    (budgetLinesChanged ? "" : "disabled") +
    ' onclick="saveAll(true)">Save Changes</button><button class="btn" onclick="loadBudgetLines(true)">Reload</button><button class="btn" onclick="addLargeDiscLine()">Add Row</button></div>';
  html +=
    '<div class="lot-table-wrap"><table class="lot-table travel-table"><thead><tr><th>Type</th><th>Description</th><th>Amount</th><th>Year</th><th>Repeat Start</th><th>Repeat End</th><th>Notes</th><th>Actions</th></tr></thead><tbody>';
  if (!lines.length) {
    html +=
      '<tr><td colspan="8" class="small" style="padding:12px">No Large Discretionary projection rows. Add Wedding, Large Gifts, or Other as needed.</td></tr>';
  }
  lines.forEach(function (l) {
    const lid = esc(l.line_id);
    const typ = largeDiscTypeFromLine(l);
    html += `<tr><td><select onchange="updateLargeDiscLine('${lid}','type',this.value)">${LARGE_DISC_TYPES.map((t) => `<option value="${esc(t)}" ${t === typ ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></td><td><input value="${esc(l.label || "")}" placeholder="Description" oninput="updateLargeDiscLine('${lid}','label',this.value)" style="width:160px"></td><td><input type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(l.amount_per_year))}" onfocus="focusBudgetMoney(this)" oninput="updateLargeDiscLineMoney('${lid}','amount_per_year',this)" onblur="blurBudgetMoney(this)" style="width:110px"></td><td><input type="number" value="${esc(l.one_time_year || "")}" placeholder="one-time" oninput="updateLargeDiscLine('${lid}','one_time_year',this.value)" style="width:90px"></td><td><input type="number" value="${esc(l.start_year || "")}" placeholder="—" oninput="updateLargeDiscLine('${lid}','start_year',this.value)" style="width:90px"></td><td><input type="number" value="${esc(l.end_year || "")}" placeholder="forever" oninput="updateLargeDiscLine('${lid}','end_year',this.value)" style="width:90px"></td><td><input value="${esc(l.notes || "")}" placeholder="Optional" oninput="updateLargeDiscLine('${lid}','notes',this.value)" style="width:180px"></td><td><button class="danger-link" onclick="deleteLargeDiscLine('${lid}')">Delete</button></td></tr>`;
  });
  html +=
    '</tbody></table></div><div class="section-note"><b>One-time lump total: $' +
    Math.round(oneTimeTotal).toLocaleString() +
    "</b> (projects only in each row's own year, never annualized)" +
    (recurringTotal
      ? " · <b>Recurring: $" +
        Math.round(recurringTotal).toLocaleString() +
        "/yr</b> (rows with a start/end range instead of a one-time year)"
      : "") +
    "</div></div>";
  return html;
}

export function renderLifestyleSpending() {
  // #269: DAF settings duplicate Special Strategies -> Charitable Giving; drop here.
  return `<div class="lifestyle-workspace"><details><summary>Travel</summary>${renderTravelBudgetPage()}</details><details><summary>Large Items</summary>${renderLargeDiscretionaryBudgetPage()}</details></div>`;
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  updateLargeDiscLineMoney,
  renderTravelBudgetPage,
  largeDiscTypeFromLine,
  largeDiscCategoryFromType,
  updateLargeDiscLine,
  addLargeDiscLine,
  deleteLargeDiscLine,
  renderLargeDiscretionaryBudgetPage,
  renderLifestyleSpending,
});
