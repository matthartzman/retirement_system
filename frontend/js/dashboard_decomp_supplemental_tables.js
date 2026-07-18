/* Supplemental editable asset/spending tables: Large Discretionary Expenses
   (travel extras), liquidity reserve-requirement buffers, and forced Roth
   conversions. Extracted verbatim from dashboard.js as part of the dashboard
   decomposition.

   Plain classic script sharing dashboard.js's global scope, loaded BEFORE
   dashboard.js in index.html so these globals are defined before dashboard.js's
   end-of-file boot runs. No logic changed; function names, module-level state
   (LIQUIDITY_ACCOUNT_OPTIONS) and behavior are byte-for-byte identical to the
   original inline block. The underlying data arrays (travelExtras,
   liquidityBuffers, forcedConversions) and their dirty flags remain declared in
   dashboard.js. */
function markTravelExtrasDirty() {
  noteSpecialSessionChange("Large Discretionary Expenses table");
  travelExtrasChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
function updateTravelExtra(i, field, val) {
  travelExtras[i][field] = val;
  markTravelExtrasDirty();
}
function addTravelExtra() {
  const newIndex = travelExtras.length;
  travelExtras.push({
    type: "",
    amount: "",
    year: "",
    start_year: "",
    end_year: "",
    comment: "",
  });
  markTravelExtrasDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector(
      `[data-travel-row="${newIndex}"] input,[data-travel-row="${newIndex}"] select`,
    );
    if (f) {
      f.focus();
      if (f.select) f.select();
    }
  }, 0);
}
async function deleteTravelExtra(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Expense Row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  travelExtras.splice(i, 1);
  markTravelExtrasDirty();
  renderMain();
}
function travelExtrasSummaryHtml() {
  if (!travelExtras.length) return "";
  const totals = {};
  let oneTime = 0,
    recurring = 0;
  travelExtras.forEach((e) => {
    const amt = Number(currencyRaw(e.amount || 0)) || 0;
    if (!amt) return;
    const key = e.type || "Uncategorized";
    totals[key] = (totals[key] || 0) + amt;
    if (e.start_year || e.end_year) recurring += amt;
    else oneTime += amt;
  });
  const chips = Object.keys(totals)
    .sort()
    .map(
      (k) =>
        `<span class="pill">${esc(k)}: ${esc(currencyDisplay(String(totals[k])))}${travelExtras.some((e) => (e.type || "Uncategorized") === k && (e.start_year || e.end_year)) ? " / yr where recurring" : ""}</span>`,
    )
    .join(" ");
  return `<div class="section-note"><b>Current planned spending in this table:</b> ${travelExtras.length} row${travelExtras.length === 1 ? "" : "s"} loaded from Plan Data. ${chips || "No amounts entered yet."}</div>`;
}
function renderTravelExtras() {
  const types = travelTypeList();
  let html = `<div class="holdings"><h3 class="group-title">Large Discretionary Expenses</h3><div class="section-note"><b>How to use this table:</b> Add one row per vacation budget, wedding, vehicle purchase, family support item, or other discretionary extra. Use <b>Year</b> for one-time spending; use <b>Repeat Start</b> and <b>Repeat End</b> for annual recurring spending. Leave unused timing fields blank. <b>Home improvement projects</b> are entered on the <b>Housing</b> tab.</div><datalist id="travelExtraTypes">${types.map((t) => `<option value="${esc(t)}"></option>`).join("")}</datalist>${travelExtrasSummaryHtml()}<div class="table-actions"><button class="btn" type="button" onclick="addTravelExtra()">Add Row</button></div><div class="lot-table-wrap"><table class="lot-table travel-table"><thead><tr><th>Type</th><th>Amount</th><th>Year</th><th>Repeat Start</th><th>Repeat End</th><th>Comment</th><th>Actions</th></tr></thead><tbody>`;
  if (!travelExtras.length) {
    html += `<tr><td colspan="7"><span class="small">No planned-spending rows yet. Click Add Row to add travel, weddings, vehicle purchases, or other extras.</span></td></tr>`;
  }
  travelExtras.forEach((e, i) => {
    html += `<tr data-travel-row="${i}"><td><select onchange="updateTravelExtra(${i},'type',this.value)"><option value="" ${!e.type ? "selected" : ""}>Choose category…</option>${types.map((t) => `<option value="${esc(t)}" ${String(e.type || "") === t ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></td><td><input type="text" value="${esc(currencyDisplay(e.amount || ""))}" placeholder="$0" onfocus="this.value=currencyRaw(this.value);this.select&&this.select()" oninput="updateTravelExtra(${i},'amount',currencyRaw(this.value))" onblur="this.value=currencyDisplay(this.value)"></td><td><input class="tiny" type="text" value="${esc(e.year || "")}" placeholder="YYYY" oninput="updateTravelExtra(${i},'year',this.value)"></td><td><input class="tiny" type="text" value="${esc(e.start_year || "")}" placeholder="YYYY" oninput="updateTravelExtra(${i},'start_year',this.value)"></td><td><input class="tiny" type="text" value="${esc(e.end_year || "")}" placeholder="YYYY" oninput="updateTravelExtra(${i},'end_year',this.value)"></td><td><input type="text" value="${esc(e.comment || "")}" oninput="updateTravelExtra(${i},'comment',this.value)"></td><td><button class="danger-link" type="button" onclick="deleteTravelExtra(${i})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div><p class="small">Tip: Type is a pick-list, but you can type your own category. If both a one-time year and repeat years are filled, the model treats the repeat start/end as the recurring schedule.</p></div>`;
  return html;
}
async function loadTravelExtras() {
  try {
    const out = await api("/api/large-discretionary-expenses");
    travelExtras = out.events || [];
    travelTypes = out.types || DEFAULT_TRAVEL_TYPES;
    travelExtrasChanged = false;
  } catch (e) {
    travelExtras = [];
    travelTypes = DEFAULT_TRAVEL_TYPES;
  }
}
async function saveTravelExtras(sync = false) {
  if (!travelExtrasChanged) return { updated: 0 };
  const out = await api("/api/large-discretionary-expenses", {
    method: "POST",
    body: JSON.stringify({ events: travelExtras, sync }),
  });
  travelExtrasChanged = false;
  return out;
}

function markLiquidityDirty() {
  noteSpecialSessionChange("Liquidity buffer table");
  liquidityChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
function updateLiquidityBuffer(i, field, val) {
  liquidityBuffers[i][field] = val;
  markLiquidityDirty();
}
const LIQUIDITY_ACCOUNT_OPTIONS = [
  "Taxable/Trust",
  "Roth",
  "IRA",
  "HSA",
  "Cash",
];
function liquidityAccountSelect(i, val) {
  return `<select onchange="updateLiquidityBuffer(${i},'reserve_account',this.value)">${LIQUIDITY_ACCOUNT_OPTIONS.map((x) => `<option value="${esc(x)}" ${String(val || "Taxable/Trust") === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>`;
}
function addLiquidityBuffer() {
  const last = liquidityBuffers[liquidityBuffers.length - 1] || {};
  const start = last.end_year ? String(Number(last.end_year) + 1) : "";
  liquidityBuffers.push({
    start_year: start,
    end_year: "",
    years_of_expenses: "0",
    reserve_account: "Taxable/Trust",
  });
  markLiquidityDirty();
  renderMain();
  setTimeout(() => {
    const el = document.querySelector(
      `[data-liquidity-row="${liquidityBuffers.length - 1}"] input`,
    );
    if (el) el.focus();
  }, 0);
}
async function deleteLiquidityBuffer(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Buffer Row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  liquidityBuffers.splice(i, 1);
  markLiquidityDirty();
  renderMain();
}
function renderLiquidityBuffers() {
  let html = `<div class="holdings"><h3 class="group-title">Reserve requirements</h3><div class="section-note"><b>Purpose:</b> A reserve requirement retains a chosen number of years of expenses for the selected year range. The default is 0 years. Add rows only when the reserve policy changes over time.</div><div class="table-actions"><button class="btn" type="button" onclick="addLiquidityBuffer()">Add reserve rule</button></div><div class="lot-table-wrap"><table class="lot-table liquidity-table"><thead><tr><th>Start year</th><th>End year</th><th>Years of expenses to retain</th><th>Reserve account</th><th></th></tr></thead><tbody>`;
  if (!liquidityBuffers.length) {
    html += `<tr><td colspan="5"><span class="small">No reserve rows yet. With no rows, the reserve requirement is 0 years.</span></td></tr>`;
  }
  liquidityBuffers.forEach((b, i) => {
    html += `<tr data-liquidity-row="${i}"><td><input type="number" value="${esc(b.start_year || "")}" oninput="updateLiquidityBuffer(${i},'start_year',this.value)"></td><td><input type="number" value="${esc(b.end_year || "")}" oninput="updateLiquidityBuffer(${i},'end_year',this.value)"></td><td><input type="text" value="${esc(b.years_of_expenses || "0")}" oninput="updateLiquidityBuffer(${i},'years_of_expenses',this.value)"></td><td>${liquidityAccountSelect(i, b.reserve_account)}</td><td><button class="danger-link" type="button" onclick="deleteLiquidityBuffer(${i})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div><p class="small">Tip: leave End year blank for an open-ended rule. If rows overlap, the first matching row is used by the model.</p></div>`;
  return html;
}
async function loadLiquidityBuffers() {
  try {
    const out = await api("/api/liquidity-buffers");
    liquidityBuffers = out.buffers || [];
    liquidityChanged = false;
  } catch (e) {
    liquidityBuffers = [];
  }
}
async function saveLiquidityBuffers(sync = false) {
  if (!liquidityChanged) return { updated: 0 };
  const out = await api("/api/liquidity-buffers", {
    method: "POST",
    body: JSON.stringify({ buffers: liquidityBuffers, sync }),
  });
  liquidityChanged = false;
  return out;
}
function forcedAccountOptions() {
  return [
    ...new Set([
      ...(forcedConversionAccounts || []),
      ...forcedConversions.map((x) => x.source_account).filter(Boolean),
    ]),
  ]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
}
function markForcedConversionsDirty() {
  noteSpecialSessionChange("Forced conversions table");
  forcedConversionsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
function updateForcedConversion(i, field, val) {
  forcedConversions[i][field] = val;
  markForcedConversionsDirty();
}
function addForcedConversion() {
  const opts = forcedAccountOptions();
  const newIndex = forcedConversions.length;
  forcedConversions.push({
    source_account: opts[0] || "",
    year: "",
    amount: "",
  });
  markForcedConversionsDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector(
      `[data-forced-row="${newIndex}"] input,[data-forced-row="${newIndex}"] select`,
    );
    if (f) {
      f.focus();
      if (f.select) f.select();
    }
  }, 0);
}
async function deleteForcedConversion(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Conversion Row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  forcedConversions.splice(i, 1);
  markForcedConversionsDirty();
  renderMain();
}
function renderForcedConversionsTable() {
  const accounts = forcedAccountOptions();
  let html = `<details class="roth-section"><summary>Forced conversions</summary><div class="field-list"><div class="section-note">Use this only for conversions that are already done or intentionally required in a scenario. Enter one row per conversion: source account, year, and dollar amount. The optimizer will not remove these rows.</div><div class="table-actions"><button class="btn" type="button" onclick="addForcedConversion()">Add Forced Conversion</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Source Account</th><th>Year</th><th>Amount</th><th>Actions</th></tr></thead><tbody>`;
  if (!forcedConversions.length) {
    html += `<tr><td colspan="4"><span class="small">No forced conversions. Click Add Forced Conversion only for already-executed or deliberately imposed conversions.</span></td></tr>`;
  }
  forcedConversions.forEach((e, i) => {
    const cur = e.source_account || "";
    html += `<tr data-forced-row="${i}"><td><select onchange="updateForcedConversion(${i},'source_account',this.value)">${accounts.map((a) => `<option value="${esc(a)}" ${a === cur ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("")}${cur && !accounts.includes(cur) ? `<option value="${esc(cur)}" selected>${esc(accountDisplayLabel(cur))}</option>` : ""}</select></td><td><input class="tiny" type="text" value="${esc(e.year || "")}" placeholder="YYYY" oninput="updateForcedConversion(${i},'year',this.value)"></td><td><input type="text" value="${esc(currencyDisplay(e.amount || ""))}" placeholder="$0" onfocus="this.value=currencyRaw(this.value);this.select&&this.select()" oninput="updateForcedConversion(${i},'amount',currencyRaw(this.value))" onblur="this.value=currencyDisplay(this.value)"></td><td><button class="danger-link" type="button" onclick="deleteForcedConversion(${i})">Delete</button></td></tr>`;
  });
  return html + `</tbody></table></div></div></details>`;
}
async function loadForcedConversions() {
  try {
    const out = await api("/api/forced-roth-conversions");
    forcedConversions = out.conversions || [];
    forcedConversionAccounts = out.accounts || [];
    forcedConversionsChanged = false;
  } catch (e) {
    forcedConversions = [];
    forcedConversionAccounts = [];
  }
}
async function saveForcedConversions(sync = false) {
  if (!forcedConversionsChanged) return { updated: 0 };
  const out = await api("/api/forced-roth-conversions", {
    method: "POST",
    body: JSON.stringify({ conversions: forcedConversions, sync }),
  });
  forcedConversionsChanged = false;
  return out;
}
