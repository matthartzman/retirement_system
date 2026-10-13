// Rental Properties page (WP12.6, design 2026-10-05 sections 3 and 6; approved mockup
// documentation/reference/wp12_screens/). Under Investments & Property: summary strip, warnings,
// property table (cards on a phone), a detail page with the tabs Basics / Income / Expenses /
// Financing / Tax / Sale / Overrides, Convert my home, and the off state ("Off . N rows entered",
// data kept, "Preview what it would add"). Data lives in the typed rental tables, read and written
// only through /api/rental/* (src/server_services/rental_service.py); the strip, warnings and
// table figures are the server's ESTIMATE from the stored properties, labelled as such.
// Helpers are bare globals; renderMain() calls renderRentalProperties(); loadAll() hands the stored
// count to setRentalKeptCount() (the nav keeps the page, in its off state, while data is kept).
// Field tiers come from the server (reference.db field_tiers): "Expert" fields show behind
// "Show advanced" unless the plan's own tier is Expert; every other field is a Standard field.

const RP_KEY = "rental_property_income";
const RP_TABS = [["basics", "Basics"], ["income", "Income"], ["expenses", "Expenses"], ["financing", "Financing"],
  ["tax", "Tax"], ["sale", "Sale"], ["overrides", "Overrides"]];
const RP_KINDS = [["standalone", "Standalone"], ["converted_home", "Converted home"]];
const RP_OWNERS = [["joint", "Joint"], ["member_1", "Member 1"], ["member_2", "Member 2"]];
// A converted home takes these from the plan's home (the parse boundary refuses them on the property).
const RP_NOT_FOR_CONVERTED = ["purchase_price", "closing_costs", "current_value", "value_as_of_year", "appreciation",
  "loan_balance", "loan_balance_year", "loan_rate", "loan_monthly_payment", "loan_term_years", "sale_year",
  "sale_month", "sale_price", "selling_cost_pct", "placed_in_service_year", "placed_in_service_month",
  "rental_start_year"];
const F = (k, l, t, extra) => Object.assign({ k, l, t }, extra || {});
// [group title, [fields]]; `only` limits a field to one kind; t: text, money, pct, year, ym, bool, select, calc.
const RP_FIELDS = {
  basics: [
    ["Identity", [F("name", "Name", "text"), F("kind", "Kind", "select", { o: RP_KINDS }),
      F("owner", "Owner", "select", { o: RP_OWNERS })]],
    ["Purchase", [
      F("purchase_year", "Purchase date", "ym", { m: "purchase_month", only: "standalone" }),
      F("purchase_year", "Purchase date (bought and lived in)", "ym", { m: "purchase_month", only: "converted_home",
        hint: "Only for the two-of-five-year section 121 test." }),
      F("purchase_price", "Purchase price", "money", { only: "standalone" }),
      F("land_share", "Land share of basis", "pct", { hint: "Not depreciable. Blank means 20%." }),
      F("closing_costs", "Closing costs added to basis", "money", { only: "standalone" }),
      F("current_value", "Current value", "money", { only: "standalone" }),
      F("value_as_of_year", "Value as of year", "year", { only: "standalone" }),
      F("appreciation", "Annual appreciation", "pct", { only: "standalone", hint: "Blank means your home's appreciation rate." })]],
    ["Converted home only", [
      F("home", "Linked home", "calc", { only: "converted_home" }),
      F("conversion_year", "Conversion date", "ym", { m: "conversion_month", only: "converted_home" }),
      F("value_at_conversion", "Value at conversion", "money", { only: "converted_home", hint: "Blank means your home's value grown to the conversion date." }),
      F("adjusted_basis_at_conversion", "Adjusted basis at conversion", "money", { only: "converted_home", hint: "Blank means your home's basis." }),
      F("dep_basis", "Depreciation basis", "calc", { only: "converted_home", hint: "Lesser of value at conversion and adjusted basis; land excluded. Computed." })]],
  ],
  income: [["Rent", [
    F("monthly_rent", "Monthly rent", "money"), F("vacancy_rate", "Vacancy", "pct"),
    F("rent_growth", "Annual rent growth", "pct", { hint: "Blank means inflation." }),
    F("rental_start_year", "Rental start year", "year", { only: "standalone", hint: "Blank means the purchase year." }),
    F("rental_end_year", "Rental end year", "year", { hint: "Blank means until sale." })]]],
  expenses: [["Operating expenses", [
    F("property_tax", "Property tax (per year)", "money"), F("property_tax_growth", "Property tax growth", "pct"),
    F("insurance", "Insurance (per year)", "money"), F("maintenance_pct", "Maintenance (% of rent)", "pct"),
    F("management_pct", "Management (% of rent)", "pct", { hint: "0% when self-managed." }),
    F("hoa", "HOA (per year)", "money"), F("utilities", "Utilities (per year)", "money"),
    F("other_expenses", "Other (per year)", "money"), F("expense_growth", "Expense growth", "pct", { hint: "Blank means inflation." })]]],
  financing: [["Loan", [
    F("loan_balance", "Balance", "money", { only: "standalone" }), F("loan_rate", "Rate", "pct", { only: "standalone" }),
    F("loan_monthly_payment", "Monthly payment", "money", { only: "standalone", hint: "Blank means computed from the term." }),
    F("loan_term_years", "Term remaining (years)", "int", { only: "standalone" }),
    F("loan_balance_year", "Balance as of year", "year", { only: "standalone" })]]],
  tax: [
    ["Depreciation", [F("placed_year", "Placed in service", "ym", { m: "placed_in_service_month", yk: "placed_in_service_year", only: "standalone" }),
      F("dep_basis", "Depreciable basis", "calc", { only: "standalone", x: true,
        hint: "Computed: (price + closing) x (1 - land share). 27.5 years, mid-month." })]],
    ["Passive loss", [
      F("active_participation", "Active participation", "bool", { hint: "Yes if you make the management decisions (approve tenants, set rent, order repairs). It enables the $25,000 allowance, which phases out between $100,000 and $150,000 of income. Most owners qualify." }),
      F("prior_suspended_loss", "Passive loss carried in", "money", { hint: "Suspended loss from before the plan." })]],
  ],
  sale: [["Sale", [
    F("sale_year", "Sale year", "ym", { m: "sale_month", only: "standalone" }),
    F("sale_price", "Sale price", "money", { only: "standalone", hint: "Type a number to override. Blank means the appreciated value." }),
    F("selling_cost_pct", "Selling cost", "pct", { only: "standalone", hint: "Blank means your home-sale cost rate." })]]],
};

let rpData = null;
let rpLoading = false;
let rpError = "";
let rpView = "list";
let rpTab = "basics";
let rpAdvanced = false;
let rpDraft = null;
let rpOrig = "";
let rpDirty = false;
let rpYear = null;
let rpMagi = 0;
let rpDismissed = new Set();
let rpWhyId = "";
let rpConvert = null;
let rpPreview = false;
let rpKept = 0;

// ── pure helpers (tested in tests/frontend/rental_properties.test.mjs) ──────────────────────
export function rentalMoney(n) {
  const v = Math.round(Number(n) || 0);
  return (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-US");
}
export function rentalPct(n) {
  return n === null || n === undefined || !Number.isFinite(Number(n)) ? "" : (Math.round(Number(n) * 1000) / 10) + "%";
}
// The input's typed text -> the stored value (money, year and int stay text for the server's parser;
// a percent is always typed as a percent: "5" and "5%" are both 0.05); "" -> null.
export function rentalParseInput(type, raw) {
  const text = String(raw ?? "").trim();
  if (!text) return null;
  if (type === "pct") {
    const n = Number(text.replace(/%$/, "").trim());
    return Number.isFinite(n) ? n / 100 : text;
  }
  if (type === "bool") return text === "yes";
  return text;
}
export function rentalDisplayValue(type, v) {
  if (v === null || v === undefined || v === "") return "";
  if (type === "pct") return Number.isFinite(Number(v)) ? String(Math.round(Number(v) * 10000) / 100) : String(v);
  return String(v);
}
const RP_RANK = { simple: 0, standard: 1, advanced: 2, expert: 3 };
// A field shows unless it is tagged Expert and neither "Show advanced" nor an Expert plan reveals it.
export function rentalFieldVisible(tier, planTier, withExpert) {
  const limit = Math.max(RP_RANK[planTier] ?? 3, RP_RANK.advanced);
  return withExpert || (RP_RANK[tier] ?? 0) <= limit;
}
export function rentalConvertedBasis(value, adjustedBasis, landShare) {
  const land = landShare === null || landShare === undefined || landShare === "" ? 0.2 : Number(landShare);
  return Math.max(0, Math.min(Number(value) || 0, Number(adjustedBasis) || 0) * (1 - land));
}
function rpMonthValue(y, m) {
  const year = String(y ?? "").trim();
  if (!/^\d{4}$/.test(year)) return "";
  return year + "-" + String(m || 7).padStart(2, "0");
}
// Payload property -> what the server stores: blanks dropped, converted-home-only rules applied.
export function rentalCleanDraft(draft) {
  const out = {};
  Object.keys(draft || {}).forEach((k) => {
    const v = draft[k];
    if (k === "improvements" || k === "overrides" || v === null || v === undefined || v === "") return;
    out[k] = v;
  });
  if (out.kind === "converted_home") RP_NOT_FOR_CONVERTED.forEach((k) => delete out[k]);
  out.improvements = ((draft || {}).improvements || []).filter((i) => i && (i.year || i.amount)).map((i) => {
    const row = {};
    Object.keys(i).forEach((k) => { if (i[k] !== null && i[k] !== "") row[k] = i[k]; });
    return row;
  });
  out.overrides = ((draft || {}).overrides || []).filter((o) => o && o.year).map((o) => {
    const row = {};
    Object.keys(o).forEach((k) => { if (o[k] !== null && o[k] !== "") row[k] = o[k]; });
    return row;
  });
  return out;
}

// ── list page ────────────────────────────────────────────────────────────────────────────────
export function rentalSummaryHtml(data, magi) {
  const s = (data || {}).summary;
  const est = (data || {}).estimate || {};
  const years = est.years || {};
  let html = '<div class="rp-estimate small">' + esc(est.label || "Estimate") + ". ";
  if (years.first !== undefined) {
    const opts = [];
    for (let y = years.first; y <= years.last; y += 1) opts.push(`<option value="${y}"${s && s.year === y ? " selected" : ""}>${y}</option>`);
    html += `<label>Year <select id="rpYear" aria-label="Summary year" onchange="rpSetYear(this.value)">${opts.join("")}</select></label> ` +
      `<label>Assumed other income (MAGI) <input id="rpMagi" aria-label="Assumed other income" type="text" inputmode="numeric" value="${esc(String(magi || 0))}" onchange="rpSetMagi(this.value)"></label>`;
  }
  html += "</div>";
  if (!s) return html + '<div class="section-note">' + esc(est.error || "Add a property to see the summary.") + "</div>";
  const card = (value, label, cls) => `<div class="review-card${cls ? " " + cls : ""}"><b>${esc(value)}</b><span>${esc(label)}</span></div>`;
  return html + '<div class="rp-strip">' +
    card(rentalMoney(s.net_cash_flow), "Annual net cash flow (" + s.year + ")") +
    card(rentalMoney(s.taxable_rental_income), "Taxable rental income (" + s.year + ")") +
    card(rentalMoney(s.suspended_loss), "Suspended losses carried (end of " + s.year + ")", s.suspended_loss > 0.5 ? "warn" : "") +
    card(rentalMoney(s.equity), "Total equity (value - loans)") + "</div>";
}

export function rentalWarningsHtml(warnings, dismissed, why, readOnly) {
  const shown = (warnings || []).filter((w) => !(dismissed && dismissed.has(w.id)));
  if (!shown.length) return "";
  const idArg = (w) => `'${esc(escJs(w.id))}'`;
  const items = shown.map((w) => {
    let actions = "";
    if (!readOnly) {
      if (w.action === "other_assets") actions += '<button class="btn warn" type="button" onclick="setStep(\'assets_special\')">Review Other Assets</button> ';
      if (w.action === "why") actions += `<button class="btn" type="button" aria-expanded="${why === w.id}" onclick="rpWhy(${idArg(w)})">Why?</button> `;
      if (w.action === "open_property") actions += `<button class="btn danger" type="button" onclick="rpOpen('${esc(escJs(w.property || ""))}')">Open property</button> `;
    }
    if (!readOnly) actions += `<button class="btn" type="button" onclick="rpDismiss(${idArg(w)})">Dismiss</button>`;
    const detail = why === w.id && w.detail ? `<div class="small rp-why">${esc(w.detail)}</div>` : "";
    return `<div class="rp-warn${w.level === "bad" ? " bad" : ""}" role="status" data-warning="${esc(w.kind)}"><span><b>${esc(w.title)}</b> ${esc(w.text)}</span><span>${actions}</span>${detail}</div>`;
  });
  return '<div class="rp-warns">' + items.join("") + "</div>";
}

const rpKindLabel = (k) => (k === "converted_home" ? "Converted home" : "Standalone");

export function rentalTableHtml(data, readOnly) {
  const list = (data || {}).table || [];
  const count = list.length;
  const act = (name) => {
    if (readOnly) return "";
    const n = `'${esc(escJs(name))}'`;
    return `<button class="btn" type="button" onclick="rpOpen(${n})">Open</button> <button class="btn" type="button" onclick="rpDuplicate(${n})">Duplicate</button> <button class="danger-link" type="button" onclick="rpRemove(${n})">Remove</button>`;
  };
  const cell = (r) => ({
    value: r.value ? rentalMoney(r.value) : "—", rent: rentalMoney(r.annual_rent) + "/yr",
    yield: r.net_yield === null || r.net_yield === undefined ? "—" : rentalPct(r.net_yield), sale: r.sale_year || "—",
  });
  let html = '<table class="rp-table"><thead><tr><th>Name</th><th>Kind</th><th class="n">Value</th><th class="n">Rent</th><th class="n">Net yield</th><th class="n">Sale year</th><th></th></tr></thead><tbody>';
  list.forEach((r) => {
    const c = cell(r);
    html += `<tr><td><b>${esc(r.name)}</b></td><td>${rpKindLabel(r.kind)}</td><td class="n">${c.value}</td><td class="n">${c.rent}</td><td class="n">${c.yield}</td><td class="n">${c.sale}</td><td>${act(r.name)}</td></tr>`;
  });
  html += '</tbody></table><div class="rp-cards">';
  list.forEach((r) => {
    const c = cell(r);
    html += `<div class="rp-card"><h3>${esc(r.name)}</h3><span class="badge ${r.kind === "converted_home" ? "warn" : "ok"}">${rpKindLabel(r.kind)}</span>` +
      `<dl><div><dt>Value</dt><dd>${c.value}</dd></div><div><dt>Rent</dt><dd>${c.rent}</dd></div><div><dt>Net yield</dt><dd>${c.yield}</dd></div><div><dt>Sale year</dt><dd>${c.sale}</dd></div></dl>${act(r.name)}</div>`;
  });
  html += "</div>";
  const max = (data || {}).max_properties || 20;
  return html + `<div class="small rp-foot">${count} of ${max} properties. Net yield = (rent - operating expenses) / value.</div>`;
}

export function rentalConvertPanelHtml(state, home) {
  if (!state) return "";
  const h = home || {};
  const basis = rentalConvertedBasis(state.value, h.adjusted_basis, 0.2);
  const row = (label, input, hint) => `<div class="field"><div><div class="field-label">${esc(label)}</div>${hint ? `<div class="unit">${esc(hint)}</div>` : ""}</div><div>${input}</div></div>`;
  return '<div class="rp-convert" role="group" aria-label="Convert my home to a rental"><h3>Convert my home to a rental</h3>' +
    "<p class=\"small\">Pre-filled from your plan's home. Change anything before creating.</p>" +
    row("Home", `<div class="field-readonly">${esc(h.label || "Your home")}</div>`) +
    row("Conversion year", `<input id="rpConvYear" aria-label="Conversion year" data-focus-key="rpConvYear" value="${esc(state.year)}" onchange="rpConvertSet('year',this.value)">`, "Defaults to your next housing move year.") +
    row("Value at conversion", `<input id="rpConvValue" aria-label="Value at conversion" data-focus-key="rpConvValue" value="${esc(state.value)}" onchange="rpConvertSet('value',this.value)">`, "Your home's value grown to that year.") +
    row("Depreciation basis", `<div class="field-readonly" id="rpConvBasis">${rentalMoney(basis)}</div>`, "Lesser of value and adjusted basis, land excluded.") +
    row("Monthly rent", `<input id="rpConvRent" aria-label="Monthly rent" data-focus-key="rpConvRent" inputmode="numeric" value="${esc(state.rent)}" onchange="rpConvertSet('rent',this.value)">`, "What you expect to charge. Required.") +
    row("Carrying costs", '<div class="field-readonly">Move to Schedule E</div>', "Mortgage, property tax, insurance, utilities and maintenance stop counting as personal spending from the conversion date.") +
    '<div class="section-note">Section 121 applies to this property only: owned and lived in 2 of the 5 years before sale. Depreciation is never excluded.</div>' +
    '<div class="rp-actions"><button class="btn" type="button" onclick="rpConvertCancel()">Cancel</button> ' +
    '<button class="btn primary" type="button" data-requires-app="1" onclick="rpConvertCreate()">Create converted home</button></div></div>';
}

export function rentalOffHtml(data, preview) {
  const n = (data || {}).count || 0;
  const meta = typeof planModuleTaxonomy === "function" ? ((planModuleTaxonomy().modules || {})[RP_KEY] || {}) : {};
  const ignored = typeof engineIgnoredWarning === "function" ? engineIgnoredWarning({ name: "Rental Properties", engine_participation: true }) : "";
  const label = n ? offRowsLabel(n) : "Off";
  let html = '<div class="rp-offbox"><div class="rp-off-head"><span class="rp-switch" aria-hidden="true"></span> <b>Rental Properties: ' + esc(label) + "</b></div>" +
    `<p class="small">${n ? `Your ${n} ${n === 1 ? "property is" : "properties are"} kept but not used: no rent, depreciation, taxes or sale in projections, and no rental lines in reports or the workbook.` : "Nothing is entered yet. Turn the feature on to add rental properties."} ${esc(ignored)}</p>` +
    '<div class="rp-actions"><button class="btn primary" type="button" data-requires-app="1" onclick="rpTurnOn()">Turn on Rental Properties</button>' +
    (n ? ` <button class="btn" type="button" aria-pressed="${!!preview}" onclick="rpPreviewToggle()">${preview ? "Hide preview" : "Preview what it would add"}</button>` : "") + "</div></div>";
  html += `<div class="section-note">${esc(meta.tier ? "Tier: " + meta.tier.charAt(0).toUpperCase() + meta.tier.slice(1) + ". " : "")}Change it in <a href="#" onclick="setStep('optional_functions');return false">Settings &gt; Plan Features</a>.</div>`;
  if (preview && n) {
    html += '<div class="section-note"><b>Preview.</b> This is what turning it on would add (read only).</div>' +
      rentalSummaryHtml(data, (data.estimate || {}).magi) + rentalWarningsHtml(data.warnings, new Set(), "", true) + rentalTableHtml(data, true);
  }
  return html;
}

function rpListHtml(data) {
  const full = data.count >= (data.max_properties || 20);
  const home = data.home || {};
  const hasConverted = (data.properties || []).some((p) => p.kind === "converted_home");
  const convertOff = !home.available || hasConverted;
  const convertWhy = !home.available ? "Your plan has no home value to convert." : hasConverted ? "Your plan's one home is already converted." : "";
  let html = '<div class="table-actions rp-head-actions">' +
    `<button class="btn primary" type="button" onclick="rpAdd()"${full ? ' disabled title="At most ' + (data.max_properties || 20) + ' properties"' : ""}>+ Add property</button>` +
    `<button class="btn good" type="button" onclick="rpConvertOpen()"${convertOff || full ? ` disabled title="${esc(convertWhy)}"` : ""}>Convert my home to a rental</button></div>`;
  if (rpConvert) html += rentalConvertPanelHtml(rpConvert, home);
  html += rentalSummaryHtml(data, rpMagi) + rentalWarningsHtml(data.warnings, rpDismissed, rpWhyId, false);
  if (!data.count) html += '<div class="section-note">No rental properties yet. Add one, or convert your home.</div>';
  else html += rentalTableHtml(data, false);
  return html;
}

// ── detail page ──────────────────────────────────────────────────────────────────────────────
function rpVisibleFields(group, kind) {
  return group.filter((f) => !f.only || f.only === kind);
}

function rpCalcText(key, draft, data) {
  const home = (data || {}).home || {};
  if (key === "home") return home.label ? home.label + " (your plan's home, Other Assets and Liabilities)" : "Your plan's home";
  const land = draft.land_share;
  if (draft.kind === "converted_home") {
    const first = (((data || {}).estimate || {}).years || {}).first;
    let value = Number(draft.value_at_conversion);
    if (!value && home.available && first) {
      const t = Math.max(0, (Number(draft.conversion_year) || first) - first + ((Number(draft.conversion_month) || 7) - 1) / 12);
      value = home.value_today * Math.pow(1 + (home.appreciation || 0), t);
    }
    const adj = Number(draft.adjusted_basis_at_conversion) || home.adjusted_basis || 0;
    return rentalMoney(rentalConvertedBasis(value, adj, land));
  }
  const cost = (Number(draft.purchase_price) || 0) + (Number(draft.closing_costs) || 0);
  return rentalMoney(cost * (1 - (land === null || land === undefined || land === "" ? 0.2 : Number(land))));
}

function rpFieldHtml(f, draft, tiers, planTier, data) {
  const key = f.yk || f.k;
  const tier = f.x ? "expert" : (tiers.property || {})[key];
  if (!rentalFieldVisible(tier, planTier, rpAdvanced)) return "";
  const badge = tier === "expert" ? ' <span class="badge exp">Expert</span>' : "";
  const hint = f.hint ? `<div class="unit">${esc(f.hint)}</div>` : "";
  const fk = `data-focus-key="rp_${esc(f.k)}"`;
  let ctl;
  if (f.t === "calc") ctl = `<div class="field-readonly" data-rp-calc="${esc(f.k)}">${esc(rpCalcText(f.k, draft, data))}</div>`;
  else if (f.t === "select") {
    const cur = draft[f.k] || f.o[0][0];
    ctl = `<select ${fk} aria-label="${esc(f.l)}" onchange="rpSet('${esc(f.k)}',this.value,'select')">` +
      f.o.map((o) => `<option value="${esc(o[0])}"${o[0] === cur ? " selected" : ""}>${esc(o[1])}</option>`).join("") + "</select>";
  } else if (f.t === "bool") {
    const cur = draft[f.k] === false ? "no" : "yes";
    ctl = `<select ${fk} aria-label="${esc(f.l)}" onchange="rpSet('${esc(f.k)}',this.value,'bool')"><option value="yes"${cur === "yes" ? " selected" : ""}>Yes</option><option value="no"${cur === "no" ? " selected" : ""}>No</option></select>`;
  } else if (f.t === "ym") {
    const yk = f.yk || f.k;
    ctl = `<input type="month" ${fk} aria-label="${esc(f.l)}" value="${esc(rpMonthValue(draft[yk], draft[f.m]))}" onchange="rpSetYm('${esc(yk)}','${esc(f.m)}',this.value)">`;
  } else {
    const unit = f.t === "pct" ? '<div class="unit">%</div>' : "";
    ctl = `<input ${fk} aria-label="${esc(f.l)}" ${f.t === "text" ? "" : 'inputmode="decimal"'} value="${esc(rentalDisplayValue(f.t, draft[f.k]))}" onchange="rpSet('${esc(f.k)}',this.value,'${f.t}')">${unit}`;
  }
  return `<div class="field"><div><div class="field-label">${esc(f.l)}${badge}</div>${hint}</div><div>${ctl}</div></div>`;
}

function rpImprovementsHtml(draft) {
  const list = draft.improvements || [];
  let html = '<div class="group-title">Capital improvements <span class="badge exp">Expert</span></div><div class="unit">Added to basis and depreciated over 27.5 years from the year placed in service.</div>';
  list.forEach((r, i) => {
    html += `<div class="field rp-row"><div><div class="field-label">Improvement ${i + 1}</div></div><div class="rp-inline">` +
      `<input aria-label="Improvement ${i + 1} year" placeholder="Year" value="${esc(r.year ?? "")}" onchange="rpChildSet('improvements',${i},'year',this.value)"> ` +
      `<input aria-label="Improvement ${i + 1} month" placeholder="Month" value="${esc(r.month ?? "")}" onchange="rpChildSet('improvements',${i},'month',this.value)"> ` +
      `<input aria-label="Improvement ${i + 1} amount" placeholder="Amount" value="${esc(r.amount ?? "")}" onchange="rpChildSet('improvements',${i},'amount',this.value)"> ` +
      `<input aria-label="Improvement ${i + 1} description" placeholder="What" value="${esc(r.description ?? "")}" onchange="rpChildSet('improvements',${i},'description',this.value)"> ` +
      `<button class="danger-link" type="button" onclick="rpChildDel('improvements',${i})">Remove</button></div></div>`;
  });
  return html + '<button class="btn" type="button" onclick="rpChildAdd(\'improvements\')">+ Add improvement</button>';
}

function rpOverridesHtml(draft) {
  if (!rpAdvanced && !rpIsExpertPlan()) {
    return '<div class="section-note"><b>Expert feature.</b> Per-year overrides replace the rent and expense formulas for years that differ. Turn on Show advanced to edit them.</div>';
  }
  const list = draft.overrides || [];
  let html = '<div class="group-title">Per-year overrides <span class="badge exp">Expert</span></div><div class="unit">A value replaces the formula for that year; leave a cell blank to keep the formula.</div>' +
    '<div class="lot-table-wrap"><table class="lot-table compact-table"><thead><tr><th>Year</th><th>Gross rent</th><th>Operating expenses</th><th>Note</th><th></th></tr></thead><tbody>';
  list.forEach((r, i) => {
    const cell = (k, label) => `<td><input aria-label="Override ${i + 1} ${label}" value="${esc(r[k] ?? "")}" onchange="rpChildSet('overrides',${i},'${k}',this.value)"></td>`;
    html += `<tr>${cell("year", "year")}${cell("gross_rent", "gross rent")}${cell("operating_expenses", "operating expenses")}${cell("notes", "note")}` +
      `<td><button class="danger-link" type="button" onclick="rpChildDel('overrides',${i})">Remove</button></td></tr>`;
  });
  return html + '</tbody></table></div><button class="btn" type="button" onclick="rpChildAdd(\'overrides\')">+ Add year</button>';
}

function rpResultsHtml(name, data) {
  const s = (data || {}).summary;
  const bp = s && s.by_property && s.by_property[name];
  if (!bp) return "";
  const row = (l, v) => `<div class="field"><div><div class="field-label">${esc(l)} <span class="badge exp">Expert</span></div></div><div><div class="field-readonly">${esc(v)}</div></div></div>`;
  return `<div class="group-title">Engine-computed, read only (end of ${s.year}; estimate)</div>` +
    row("Accumulated depreciation", rentalMoney(bp.accumulated_depreciation)) + row("Suspended passive loss carried", rentalMoney(bp.suspended_loss));
}

function rpIsExpertPlan() {
  return (typeof currentPlanTier === "function" ? currentPlanTier() : "") === "expert";
}

function rpTabBodyHtml(draft, data) {
  const tiers = (data || {}).field_tiers || {};
  const planTier = typeof currentPlanTier === "function" ? currentPlanTier() : "";
  const kind = draft.kind === "converted_home" ? "converted_home" : "standalone";
  if (rpTab === "overrides") return rpOverridesHtml(draft);
  let html = "";
  (RP_FIELDS[rpTab] || []).forEach(([title, fields]) => {
    const body = rpVisibleFields(fields, kind).map((f) => rpFieldHtml(f, draft, tiers, planTier, data)).join("");
    if (body) html += `<div class="group-title">${esc(title)}</div>` + body;
  });
  if (rpTab === "financing" && kind === "converted_home") html += '<div class="section-note">A converted home keeps your plan\'s own mortgage for the home.</div>';
  if (rpTab === "sale") html += `<div class="section-note">${kind === "converted_home" ? "A converted home is sold with your plan's home (Other Assets and Liabilities). " : ""}Gain, depreciation recapture (capped at 25%) and the tax at sale are computed by the projection. A loss on the sale is treated as ordinary.</div>`;
  if (rpTab === "tax") html += (rpAdvanced || rpIsExpertPlan() ? rpImprovementsHtml(draft) + rpResultsHtml(draft.name, data) : "");
  if (!html) html = '<div class="section-note">Nothing to enter here for this kind of property.</div>';
  return html;
}

export function rentalDetailHtml(draft, data) {
  const isNew = !rpOrig;
  const tabs = RP_TABS.map(([id, label]) => `<button class="rp-tab${rpTab === id ? " on" : ""}" type="button" role="tab" aria-selected="${rpTab === id}" onclick="rpTabSet('${id}')">${label}</button>`).join("");
  const owner = (RP_OWNERS.find((o) => o[0] === draft.owner) || RP_OWNERS[0])[1].toLowerCase();
  const saved = !isNew ? `<button class="btn" type="button" onclick="rpDuplicate('${esc(escJs(rpOrig))}')">Duplicate</button><button class="btn danger" type="button" onclick="rpRemove('${esc(escJs(rpOrig))}')">Remove</button>` : "";
  return '<div class="rp-detail"><div class="rp-crumb small">Investments &amp; Property &gt; Rental Properties &gt; ' + esc(draft.name || "New property") + "</div>" +
    `<h3 class="rp-title">${esc(draft.name || "New property")}</h3><div class="small">${rpKindLabel(draft.kind)} &middot; owned ${esc(owner)}</div>` +
    '<div class="table-actions"><button class="btn" type="button" onclick="rpBack()">&larr; Back to list</button>' +
    '<button class="btn primary" type="button" data-requires-app="1" onclick="rpSave()">Save property</button>' + saved +
    (rpDirty ? ' <span class="status unsaved" id="rpDirtyBadge">Unsaved changes</span>' : "") + "</div>" +
    `<div class="rp-tabs" role="tablist">${tabs}</div>` +
    '<div class="rp-advbar"><span class="small">' + (rpAdvanced ? "Showing Standard + Expert fields." : "Showing Standard fields only.") + ' <span class="badge exp">Expert</span> = advanced field.</span>' +
    `<label><input type="checkbox" id="rpAdvanced"${rpAdvanced ? " checked" : ""} onchange="rpToggleAdvanced()"> <b>Show advanced</b></label></div>` +
    '<div class="field-list rp-fields">' + rpTabBodyHtml(draft, data) + "</div></div>";
}

// ── page ─────────────────────────────────────────────────────────────────────────────────────
export function renderRentalProperties() {
  if (rpData === null) {
    if (!rpLoading && !rpError) loadRentalProperties();
    return `<div class="field-list">${rpError ? `<div class="section-note">${esc(rpError)} <button class="btn" type="button" onclick="loadRentalProperties()">Retry</button></div>` : '<div class="section-note">Loading rental properties…</div>'}</div>`;
  }
  const body = !rpData.enabled ? rentalOffHtml(rpData, rpPreview) : rpView === "detail" && rpDraft ? rentalDetailHtml(rpDraft, rpData) : rpListHtml(rpData);
  return `<div class="field-list rp-page">${body}</div>`;
}

export async function loadRentalProperties() {
  rpLoading = true;
  rpError = "";
  try {
    const q = new URLSearchParams();
    if (rpYear) q.set("year", rpYear);
    if (rpMagi) q.set("magi", rpMagi);
    const out = await api("/api/rental/properties" + (q.toString() ? "?" + q : ""));
    rpData = out && out.success ? out : null;
    if (!rpData) rpError = "Rental properties could not be loaded.";
  } catch (e) {
    rpData = null;
    rpError = "Rental properties could not be loaded: " + e.message;
  }
  rpLoading = false;
  renderMain();
}

export function setRentalKeptCount(n) {
  rpKept = Number(n) || 0;
  rpData = null; // the plan (or its switch) changed: the next render reads the page again
  rpConvert = null;
}
export function rentalKeptCount() {
  return rpKept;
}

function rpEdit(name) {
  const p = ((rpData || {}).properties || []).find((x) => x.name === name);
  rpDraft = JSON.parse(JSON.stringify(p || { name: "", kind: "standalone", active_participation: true }));
  rpDraft.improvements = rpDraft.improvements || [];
  rpDraft.overrides = rpDraft.overrides || [];
  rpOrig = p ? p.name : "";
  rpDirty = false;
  rpTab = "basics";
  rpView = "detail";
}

export function rpOpen(name) { rpEdit(name); renderMain(); }
export function rpAdd() { rpConvert = null; rpEdit(""); renderMain(); }
export function rpTabSet(id) { rpTab = id; renderMain(); }
export function rpToggleAdvanced() { rpAdvanced = !rpAdvanced; renderMain(); }
export function rpDismiss(id) { rpDismissed.add(id); renderMain(); }
export function rpWhy(id) { rpWhyId = rpWhyId === id ? "" : id; renderMain(); }
export function rpPreviewToggle() { rpPreview = !rpPreview; renderMain(); }
export function rpSetYear(v) { rpYear = Number(v) || null; loadRentalProperties(); }
export function rpSetMagi(v) { rpMagi = Math.max(0, Number(String(v).replace(/[^0-9.]/g, "")) || 0); loadRentalProperties(); }
export function rpTurnOn() { return setPlanFeatureSwitch(RP_KEY, true); }

function rpTouch() {
  rpDirty = true;
  const bar = document.querySelector(".rp-detail .table-actions");
  if (bar && !document.getElementById("rpDirtyBadge")) bar.insertAdjacentHTML("beforeend", ' <span class="status unsaved" id="rpDirtyBadge">Unsaved changes</span>');
  document.querySelectorAll("[data-rp-calc]").forEach((el) => { el.textContent = rpCalcText(el.getAttribute("data-rp-calc"), rpDraft, rpData); });
}
export function rpSet(key, raw, type) {
  const v = rentalParseInput(type, raw);
  if (v === null) delete rpDraft[key];
  else rpDraft[key] = v;
  if (key === "kind") { rpDirty = true; renderMain(); return; }
  rpTouch();
}
export function rpSetYm(yk, mk, value) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(value || ""));
  if (m) { rpDraft[yk] = m[1]; rpDraft[mk] = String(Number(m[2])); } else { delete rpDraft[yk]; delete rpDraft[mk]; }
  rpTouch();
}
export function rpChildSet(list, i, key, raw) { const v = String(raw ?? "").trim(); rpDraft[list][i][key] = v === "" ? null : v; rpTouch(); }
export function rpChildAdd(list) { rpDraft[list].push(list === "overrides" ? { year: "" } : { year: "", amount: "" }); rpDirty = true; renderMain(); }
export function rpChildDel(list, i) { rpDraft[list].splice(i, 1); rpDirty = true; renderMain(); }

export async function rpBack() {
  if (rpDirty && !(await showInAppConfirm("Your changes to this property have not been saved.", { title: "Discard changes?", confirmLabel: "Discard", variant: "danger" }))) return;
  rpView = "list"; rpDraft = null; rpDirty = false; renderMain();
}

export async function rpSave() {
  const body = { property: rentalCleanDraft(rpDraft) };
  if (rpOrig) body.original_name = rpOrig;
  try {
    const out = await api("/api/rental/property", { method: "POST", body: JSON.stringify(body) });
    rpDirty = false;
    setRentalKeptCount(out.count);
    await loadRentalProperties();
    rpEdit(out.property.name);
    renderMain();
    showMessage("Saved " + out.property.name + ".");
  } catch (e) {
    showMessage("Could not save the property: " + e.message, "error");
  }
}

export async function rpDuplicate(name) {
  try {
    const out = await api("/api/rental/property/duplicate", { method: "POST", body: JSON.stringify({ name }) });
    rpView = "list"; rpDraft = null; rpDirty = false;
    setRentalKeptCount(out.count);
    await loadRentalProperties();
    showMessage("Created " + out.property.name + ".");
  } catch (e) {
    showMessage("Could not duplicate: " + e.message, "error");
  }
}

export async function rpRemove(name) {
  if (!(await showInAppConfirm("This removes the property with its improvements and overrides. It cannot be undone.", { title: "Remove " + name + "?", confirmLabel: "Remove", variant: "danger" }))) return;
  try {
    const out = await api("/api/rental/property/delete", { method: "POST", body: JSON.stringify({ name }) });
    rpView = "list"; rpDraft = null; rpDirty = false;
    setRentalKeptCount(out.count);
    await loadRentalProperties();
    showMessage("Removed " + name + ".");
  } catch (e) {
    showMessage("Could not remove: " + e.message, "error");
  }
}

export function rpConvertOpen() {
  const h = (rpData || {}).home || {};
  if (!h.available) return;
  rpConvert = { year: String(h.conversion_year), value: String(h.value_at_conversion), prefill: h.value_at_conversion, rent: "" };
  renderMain();
}
export function rpConvertSet(key, raw) {
  rpConvert[key] = String(raw ?? "").trim();
  const el = document.getElementById("rpConvBasis");
  if (el) el.textContent = rentalMoney(rentalConvertedBasis(Number(rpConvert.value), ((rpData || {}).home || {}).adjusted_basis, 0.2));
}
export function rpConvertCancel() { rpConvert = null; renderMain(); }
export async function rpConvertCreate() {
  const c = rpConvert;
  if (!c || !String(c.rent).trim()) { showMessage("Enter the monthly rent you expect to charge.", "error"); return; }
  const prop = { name: "Primary residence (converted home)", kind: "converted_home", conversion_year: c.year, monthly_rent: c.rent };
  if (String(c.value) !== String(c.prefill)) prop.value_at_conversion = c.value;
  try {
    const out = await api("/api/rental/property", { method: "POST", body: JSON.stringify({ property: prop }) });
    rpConvert = null;
    setRentalKeptCount(out.count);
    await loadRentalProperties();
    rpOpen(out.property.name);
    showMessage("Converted your home to a rental.");
  } catch (e) {
    showMessage("Could not convert your home: " + e.message, "error");
  }
}

Object.assign(window, {
  rentalMoney, rentalPct, rentalParseInput, rentalDisplayValue, rentalFieldVisible, rentalConvertedBasis,
  rentalCleanDraft, rentalSummaryHtml, rentalWarningsHtml, rentalTableHtml, rentalConvertPanelHtml, rentalOffHtml,
  rentalDetailHtml, renderRentalProperties, loadRentalProperties, setRentalKeptCount, rentalKeptCount,
  rpOpen, rpAdd, rpTabSet, rpToggleAdvanced, rpDismiss, rpWhy, rpPreviewToggle, rpSetYear, rpSetMagi, rpTurnOn,
  rpSet, rpSetYm, rpChildSet, rpChildAdd, rpChildDel, rpBack, rpSave, rpDuplicate, rpRemove,
  rpConvertOpen, rpConvertSet, rpConvertCancel, rpConvertCreate,
});
