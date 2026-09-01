export async function loadTravelExtras() {
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
export async function saveTravelExtras(sync = false) {
  if (!travelExtrasChanged) return { updated: 0 };
  const out = await api("/api/large-discretionary-expenses", {
    method: "POST",
    body: JSON.stringify({ events: travelExtras, sync }),
  });
  travelExtrasChanged = false;
  return out;
}

export function markLiquidityDirty() {
  noteSpecialSessionChange("Liquidity buffer table");
  liquidityChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
export function updateLiquidityBuffer(i, field, val) {
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
export function liquidityAccountSelect(i, val) {
  return `<select onchange="updateLiquidityBuffer(${i},'reserve_account',this.value)">${LIQUIDITY_ACCOUNT_OPTIONS.map((x) => `<option value="${esc(x)}" ${String(val || "Taxable/Trust") === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>`;
}
export function addLiquidityBuffer() {
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
export async function deleteLiquidityBuffer(i) {
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
export function renderLiquidityBuffers() {
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
export async function loadLiquidityBuffers() {
  try {
    const out = await api("/api/liquidity-buffers");
    liquidityBuffers = out.buffers || [];
    liquidityChanged = false;
  } catch (e) {
    liquidityBuffers = [];
  }
}
export async function saveLiquidityBuffers(sync = false) {
  if (!liquidityChanged) return { updated: 0 };
  const out = await api("/api/liquidity-buffers", {
    method: "POST",
    body: JSON.stringify({ buffers: liquidityBuffers, sync }),
  });
  liquidityChanged = false;
  return out;
}
export function forcedAccountOptions() {
  return [
    ...new Set([
      ...(forcedConversionAccounts || []),
      ...forcedConversions.map((x) => x.source_account).filter(Boolean),
    ]),
  ]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
}
export function markForcedConversionsDirty() {
  noteSpecialSessionChange("Forced conversions table");
  forcedConversionsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
export function updateForcedConversion(i, field, val) {
  forcedConversions[i][field] = val;
  markForcedConversionsDirty();
}
export function addForcedConversion() {
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
export async function deleteForcedConversion(i) {
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
export function renderForcedConversionsTable() {
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
export async function loadForcedConversions() {
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
export async function saveForcedConversions(sync = false) {
  if (!forcedConversionsChanged) return { updated: 0 };
  const out = await api("/api/forced-roth-conversions", {
    method: "POST",
    body: JSON.stringify({ conversions: forcedConversions, sync }),
  });
  forcedConversionsChanged = false;
  return out;
}

// #299: house sale proceeds split across multiple accounts by percentage.
// Same client-state/add/delete/render shape as liquidityBuffers and
// forcedConversions above -- one in-memory array, saved as a whole list to
// a single endpoint (/api/home-sale-splits), rather than per-row CSV writes.
export async function loadHomeSaleSplits() {
  try {
    const out = await api("/api/home-sale-splits");
    homeSaleSplits = out.splits || [];
    homeSaleSplitAccounts = out.accounts || [];
    homeSaleSplitsChanged = false;
  } catch (e) {
    homeSaleSplits = [];
    homeSaleSplitAccounts = [];
  }
}
export async function saveHomeSaleSplits(sync = false) {
  if (!homeSaleSplitsChanged) return { updated: 0 };
  const out = await api("/api/home-sale-splits", {
    method: "POST",
    body: JSON.stringify({ splits: homeSaleSplits, sync }),
  });
  homeSaleSplitsChanged = false;
  return out;
}
export function markHomeSaleSplitsDirty() {
  noteSpecialSessionChange("Home sale split table");
  homeSaleSplitsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
export function updateHomeSaleSplit(i, field, val) {
  homeSaleSplits[i][field] = val;
  markHomeSaleSplitsDirty();
}
export function addHomeSaleSplit() {
  const used = new Set(homeSaleSplits.map((s) => s.account));
  const nextAcct =
    homeSaleSplitAccounts.find((a) => !used.has(a)) ||
    homeSaleSplitAccounts[0] ||
    "";
  const newIndex = homeSaleSplits.length;
  homeSaleSplits.push({ account: nextAcct, percentage: "" });
  markHomeSaleSplitsDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector(
      `[data-home-sale-split-row="${newIndex}"] input,[data-home-sale-split-row="${newIndex}"] select`,
    );
    if (f) {
      f.focus();
      if (f.select) f.select();
    }
  }, 0);
}
export async function deleteHomeSaleSplit(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Split Row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  homeSaleSplits.splice(i, 1);
  markHomeSaleSplitsDirty();
  renderMain();
}
export function homeSaleSplitPctTotal() {
  return homeSaleSplits.reduce(
    (sum, s) => sum + (numberFromDisplay(s.percentage) || 0),
    0,
  );
}
export function renderHomeSaleSplits() {
  const total = homeSaleSplitPctTotal();
  const totalOk = homeSaleSplits.length === 0 || Math.abs(total - 100) < 0.01;
  let html = `<div class="holdings"><h3 class="group-title">Split sale proceeds across accounts</h3><div class="section-note">Optional: divide house sale proceeds across more than one account by percentage instead of depositing the full amount to a single account above. Leave empty to use the single account setting instead. Rows must sum to 100%.</div><div class="table-actions"><button class="btn" type="button" onclick="addHomeSaleSplit()">Add split row</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Account</th><th>Percentage</th><th></th></tr></thead><tbody>`;
  if (!homeSaleSplits.length) {
    html += `<tr><td colspan="3"><span class="small">No split rows. The single account setting above is used.</span></td></tr>`;
  }
  homeSaleSplits.forEach((s, i) => {
    const cur = s.account || "";
    const accts = homeSaleSplitAccounts;
    html += `<tr data-home-sale-split-row="${i}"><td><select onchange="updateHomeSaleSplit(${i},'account',this.value)">${accts.map((a) => `<option value="${esc(a)}" ${a === cur ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("")}${cur && !accts.includes(cur) ? `<option value="${esc(cur)}" selected>${esc(accountDisplayLabel(cur))}</option>` : ""}</select></td><td><input class="tiny" type="text" value="${esc(s.percentage || "")}" placeholder="0%" oninput="updateHomeSaleSplit(${i},'percentage',this.value)"></td><td><button class="danger-link" type="button" onclick="deleteHomeSaleSplit(${i})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div>`;
  if (homeSaleSplits.length) {
    html += `<div class="section-note${totalOk ? " ok" : " warning"}">Total: ${total.toFixed(1)}%${totalOk ? "" : " — must equal 100% before saving"}</div>`;
  }
  html += `</div>`;
  return html;
}

// Wave 6.4 ("leaves inward" ES-module migration): converted to a real ES
// module. No cross-file mutable state (verified: nothing outside this file
// reads or writes this file's module-level consts/let), so only the
// functions below need the window bridge, for dashboard.js's calls and this
// file's own inline onclick/oninput HTML attributes.
Object.assign(window, {
  
  
  
  
  
  
  loadTravelExtras,
  saveTravelExtras,
  markLiquidityDirty,
  updateLiquidityBuffer,
  liquidityAccountSelect,
  addLiquidityBuffer,
  deleteLiquidityBuffer,
  renderLiquidityBuffers,
  loadLiquidityBuffers,
  saveLiquidityBuffers,
  forcedAccountOptions,
  markForcedConversionsDirty,
  updateForcedConversion,
  addForcedConversion,
  deleteForcedConversion,
  renderForcedConversionsTable,
  loadForcedConversions,
  saveForcedConversions,
  loadHomeSaleSplits,
  saveHomeSaleSplits,
  markHomeSaleSplitsDirty,
  updateHomeSaleSplit,
  addHomeSaleSplit,
  deleteHomeSaleSplit,
  homeSaleSplitPctTotal,
  renderHomeSaleSplits,
});
