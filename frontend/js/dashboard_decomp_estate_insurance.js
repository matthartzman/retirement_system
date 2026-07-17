/* Estate planning and insurance-in-force UI, extracted verbatim from
   dashboard.js as part of the dashboard decomposition.

   Plain classic script sharing dashboard.js's global scope, loaded BEFORE
   dashboard.js in index.html so these globals are defined before dashboard.js's
   end-of-file boot runs. No logic changed; function names, globals, and
   behavior are byte-for-byte identical to the original inline block.

   Owns: the Estate Information page (federal/state exemptions, trusts, gifting,
   step-up, special-needs, other), the insurance-policy group renderer, and the
   life / non-life insurance policy pages plus their add/delete handlers. */
async function loadEstateStateOptions() {
  try {
    const out = await api("/api/estate-state-options");
    estateStateOptions = out.states || [];
  } catch (e) {
    estateStateOptions = [];
  }
}
function stateLikeEstateSubsection(sub) {
  const n = norm(sub);
  return (
    ![
      "federal",
      "gifting",
      "trust_structure",
      "step_up",
      "qtip_trust",
      "credit_shelter_trust",
      "sn_beneficiary",
      "sn_trust",
      "sn_able",
      "sn_govbenefits",
    ].includes(n) && !n.startsWith("trust_account")
  );
}
function estateRowsBySub(sub) {
  return rowsForStep("estate").filter(
    (r) => String(r.subsection || "") === String(sub || ""),
  );
}
function renderEstateSection(title, desc, rs, open = false) {
  if (!rs.length) return "";
  return `<details ${open ? "open" : ""}><summary>${esc(title)}</summary><div class="field-list"><div class="section-note">${esc(desc)}</div>${rs.map(fieldHtml).join("")}</div></details>`;
}
function renderEstateStatesTable() {
  const all = estateStateOptions.length ? estateStateOptions : [];
  const existingSubs = [
    ...new Set(
      rowsForStep("estate")
        .map((r) => String(r.subsection || ""))
        .filter(stateLikeEstateSubsection),
    ),
  ];
  let html = `<details open><summary>Exemption: State estate-tax references</summary><div class="field-list"><div class="section-note">States below come from reference_data/state_tax.csv. Add a state to Plan Data when it should appear in the estate-analysis inputs.</div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>State</th><th>Estate tax</th><th>Reference exemption</th><th>Plan Data status</th><th>Action</th></tr></thead><tbody>`;
  const names = new Set([...all.map((s) => s.state), ...existingSubs]);
  [...names]
    .sort((a, b) => a.localeCompare(b))
    .forEach((name) => {
      const opt = all.find((s) => s.state === name) || {};
      const has = existingSubs.includes(name);
      html += `<tr><td><b>${esc(name)}</b></td><td>${esc(String(opt.estate || ""))}</td><td>${esc(opt.estate_exempt ? currencyDisplay(opt.estate_exempt) : "n/a")}</td><td>${has ? "Included in Plan Data" : "Reference only"}</td><td>${has ? '<span class="small">editable below</span>' : `<button class="btn" type="button" data-requires-app="1" onclick="addEstateState('${esc(name)}')">Add state</button>`}</td></tr>`;
    });
  html += `</tbody></table></div></div></details>`;
  return html;
}
async function addEstateState(state) {
  try {
    state =
      state ||
      (await showInAppPrompt("State abbreviation or name:", "", {
        title: "Add Estate State",
        placeholder: "e.g. CA, NY",
      }));
    if (!state) return;
    const out = await api("/api/estate-state/add", {
      method: "POST",
      body: JSON.stringify({ state }),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "estate";
    showMessage(out.message || "State added.");
  } catch (e) {
    showMessage("Error adding estate state: " + e.message, "error");
  }
}
async function addTrustAccount() {
  try {
    const name = await showInAppPrompt("Trust account name:", "", {
      title: "Add Trust Account",
    });
    if (!name) return;
    const rawType = await showInAppPrompt("Trust type:", "Revocable", {
      title: "Trust Type",
      placeholder:
        "Revocable, Irrevocable, Credit Shelter, QTIP, Special Needs, Other",
    });
    if (rawType === null) return;
    const type = rawType || "Revocable";
    const out = await api("/api/trust-account/add", {
      method: "POST",
      body: JSON.stringify({ account_name: name, trust_type: type }),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "estate";
    showMessage(out.message || "Trust account added.");
  } catch (e) {
    showMessage("Error adding trust account: " + e.message, "error");
  }
}
function renderTrustAccountsTable() {
  const estate = rowsForStep("estate");
  const trustRows = estate.filter((r) =>
    norm(r.subsection).startsWith("trust_account"),
  );
  const bySub = {};
  trustRows.forEach((r) => {
    (bySub[r.subsection] || (bySub[r.subsection] = [])).push(r);
  });
  let html = `<details open><summary>Trusts</summary><div class="field-list"><div class="section-note">Trust accounts are shown in a compact table. Each trust has a type pulldown and can be expanded for additional fields.</div><div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addTrustAccount()">Add trust account</button></div>`;
  const subs = Object.keys(bySub).sort();
  if (!subs.length) {
    html += `<p class="small">No explicit trust-account rows yet. Investment accounts with Trust in the account name still flow through the holdings page; add trust rows here when you want estate metadata.</p>`;
  }
  subs.forEach((sub) => {
    const rs = bySub[sub];
    const name = rs.find((r) => norm(r.label) === "account_name");
    const typ = rs.find((r) => norm(r.label) === "trust_type");
    html += `<details><summary>${esc(translatePersonPlaceholders(name ? valOf(name) : sub))} · ${typ ? `<select onclick="event.stopPropagation()" onchange="editValue(${typ.row_index},this.value,this)">${["Revocable", "Irrevocable", "Credit Shelter", "QTIP", "Special Needs", "Other"].map((x) => `<option value="${esc(x)}" ${norm(valOf(typ)) === norm(x) ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>` : esc(translatePersonPlaceholders(sub))}</summary><div class="field-list">${rs.map(fieldHtml).join("")}</div></details>`;
  });
  html += `</div></details>`;
  return html;
}
function renderToggleRows(title, description, rs, open = false) {
  if (!rs.length) return "";
  const enabled = rs.find((r) => norm(r.label) === "enabled");
  let shown = rs;
  if (enabled && !boolishValue(enabled)) shown = [enabled];
  else if (enabled) shown = [enabled, ...rs.filter((r) => r !== enabled)];
  return renderEstateSection(
    title,
    description,
    sortRowsByDependency(shown),
    open,
  );
}
function renderEstateInformation() {
  if (searchText.trim()) return renderFields("estate");
  const estate = rowsForStep("estate");
  const federal = estate.filter((r) => r.subsection === "Federal");
  const stateSubs = [
    ...new Set(
      estate
        .map((r) => String(r.subsection || ""))
        .filter(stateLikeEstateSubsection),
    ),
  ];
  let html = renderEstateSection(
    "Exemption: Federal",
    "Federal estate exemption and portability inputs.",
    sortRowsByDependency(federal),
    true,
  );
  html += renderEstateStatesTable();
  stateSubs.forEach((sub) => {
    html += renderEstateSection(
      "Exemption: " + sub,
      `${sub} estate-tax rows included in Plan Data.`,
      sortRowsByDependency(estateRowsBySub(sub)),
      false,
    );
  });
  html += renderTrustAccountsTable();
  html += renderToggleRows(
    "QTIP Trust",
    "Start with Enabled. Trust mechanics appear only when this trust is enabled.",
    estate.filter((r) => r.subsection === "QTIP Trust"),
    false,
  );
  html += renderToggleRows(
    "Credit Shelter Trust",
    "Start with Enabled. Credit shelter mechanics appear only when this trust is enabled.",
    estate.filter((r) => r.subsection === "Credit Shelter Trust"),
    true,
  );
  html += renderEstateSection(
    "Gifting",
    "Annual gift exclusion, planned gifting, and related transfer assumptions.",
    sortRowsByDependency(estate.filter((r) => r.subsection === "Gifting")),
    false,
  );
  html += renderEstateSection(
    "Basis step-up",
    "Taxable-account basis step-up and property-regime assumptions.",
    sortRowsByDependency(estate.filter((r) => r.subsection === "Step-Up")),
    false,
  );
  html += renderEstateSection(
    "Beneficiary support and special-needs planning",
    "Enable Special Needs Planning in Optional workbook modules to edit ABLE/trust/government-benefit rows.",
    sortRowsByDependency(
      optionalFunctionEnabled("special_needs_planning")
        ? estate.filter((r) => norm(r.subsection).startsWith("sn_"))
        : [],
    ),
    false,
  );
  const other = estate.filter(
    (r) =>
      r.section !== "Insurance In Force" &&
      !federal.includes(r) &&
      !stateLikeEstateSubsection(r.subsection) &&
      !["QTIP Trust", "Credit Shelter Trust", "Gifting", "Step-Up"].includes(
        r.subsection,
      ) &&
      !norm(r.subsection).startsWith("sn_") &&
      !norm(r.subsection).startsWith("trust_account"),
  );
  html += renderEstateSection(
    "Other estate information",
    "Additional estate-planning rows.",
    sortRowsByDependency(other),
    false,
  );
  html += renderNonLifeInsurancePolicies();
  return html;
}

const INSURANCE_POLICY_TYPES = [
  "Life",
  "Disability",
  "Long-Term Care",
  "Umbrella",
  "Auto",
  "Home",
  "Property and Casualty",
  "Other",
];
const NON_LIFE_INSURANCE_POLICY_TYPES = INSURANCE_POLICY_TYPES.filter(
  (t) => t !== "Life",
);
let newInsurancePolicyType = "Life";
function setNewInsurancePolicyType(v) {
  newInsurancePolicyType = v || "Life";
}
function inferPolicyType(sub, rs) {
  const tr = rs.find((r) => ["policy_type", "type"].includes(norm(r.label)));
  const v = tr ? String(valOf(tr) || "").trim() : "";
  const text = (v || sub || "").toLowerCase();
  if (text.includes("disability") || text.startsWith("di") || text === "group")
    return "Disability";
  if (text.includes("umbrella")) return "Umbrella";
  if (text.includes("auto")) return "Auto";
  if (text.includes("home") || text.includes("ho")) return "Home";
  if (text.includes("property") || text.startsWith("pc"))
    return "Property and Casualty";
  if (text.includes("ltc") || text.includes("long")) return "Long-Term Care";
  if (text.includes("life") || text.includes("term") || text.includes("whole"))
    return "Life";
  return v || "Other";
}
function policyTypeRow(rs) {
  return rs.find((r) => ["policy_type", "type"].includes(norm(r.label)));
}
function policyTypeSelect(r, current, choices) {
  if (!r) return `<span class="small">${esc(current)}</span>`;
  const opts = choices || INSURANCE_POLICY_TYPES;
  return `<select onclick="event.stopPropagation()" onchange="editValue(${r.row_index},this.value,this)">${opts.map((t) => `<option value="${esc(t)}" ${norm(current) === norm(t) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
}
function renderInsurancePolicyGroup(opts) {
  const { stepId, rs, life, title, addLabel } = opts;
  const types = life ? ["Life"] : NON_LIFE_INSURANCE_POLICY_TYPES;
  const counts = rs.filter((r) => norm(r.label) === "policy_count");
  const policyRows = rs.filter(
    (r) =>
      norm(r.label) !== "policy_count" &&
      !/scenario|targets/i.test(String(r.subsection || "")),
  );
  const other = rs.filter(
    (r) =>
      norm(r.label) !== "policy_count" &&
      /scenario|targets/i.test(String(r.subsection || "")),
  );
  const bySub = {};
  policyRows.forEach((r) => {
    (bySub[r.subsection] || (bySub[r.subsection] = [])).push(r);
  });
  let html = `<div class="holdings"><h3 class="group-title">${esc(title)}</h3><div class="section-note"><b>How to use this page:</b> each policy appears as a collapsible section with a policy-type pulldown. Premium-end and term-end fields are YYYY year inputs. Add another policy from the selector below; duplicate types receive a sequential number.</div><div class="table-actions"><select onchange="setNewInsurancePolicyType(this.value)">${types.map((t) => `<option value="${esc(t)}" ${t === newInsurancePolicyType ? "selected" : ""}>${esc(t)}</option>`).join("")}</select><button class="btn" type="button" data-requires-app="1" onclick="addInsurancePolicy()">${esc(addLabel)}</button></div></div>`;
  let counters = {};
  Object.keys(bySub)
    .sort()
    .forEach((sub) => {
      const prs = bySub[sub];
      const typ = inferPolicyType(sub, prs);
      const k = norm(typ);
      counters[k] = (counters[k] || 0) + 1;
      const typeRow = policyTypeRow(prs);
      const body = prs
        .filter((r) => r !== typeRow)
        .map(fieldHtml)
        .join("");
      html += `<details><summary><span>${esc(typ)} ${counters[k]} · ${esc(sub)}</span> ${policyTypeSelect(typeRow, typ, types)} <button class="danger-link" type="button" onclick="deleteInsurancePolicy(event,'${escJs(sub)}')">Delete</button></summary><div class="field-list">${body}</div></details>`;
    });
  if (counts.length)
    html += renderEstateSection(
      "Policy counts / coverage inventory",
      "Summary counts by policy family.",
      counts,
      false,
    );
  if (other.length)
    html += renderEstateSection(
      "Policy scenarios and targets",
      "Scenario controls and target coverage assumptions.",
      other,
      false,
    );
  return html;
}
function renderLifeInsurancePolicies() {
  const rs = rowsForStep("annuity_death_benefits").filter(
    (r) => r.section === "Insurance In Force",
  );
  newInsurancePolicyType = "Life";
  return renderInsurancePolicyGroup({
    stepId: "annuity_death_benefits",
    rs,
    life: true,
    title: "Insurance Policies (Life)",
    addLabel: "Add life insurance policy",
  });
}
function renderNonLifeInsurancePolicies() {
  const rs = rowsForStep("estate").filter(
    (r) => r.section === "Insurance In Force",
  );
  if (newInsurancePolicyType === "Life") newInsurancePolicyType = "Disability";
  return renderInsurancePolicyGroup({
    stepId: "estate",
    rs,
    life: false,
    title:
      "Protection Policies (Disability, Long-Term Care, Umbrella, Property & Casualty)",
    addLabel: "Add protection policy",
  });
}
async function addInsurancePolicy() {
  try {
    const out = await api("/api/insurance-policy/add", {
      method: "POST",
      body: JSON.stringify({ policy_type: newInsurancePolicyType }),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep =
      norm(newInsurancePolicyType) === "life"
        ? "annuity_death_benefits"
        : "estate";
    showMessage(out.message || "Policy added.");
  } catch (e) {
    showMessage("Error adding policy: " + e.message, "error");
  }
}
async function deleteInsurancePolicy(evt, subsection) {
  if (evt && evt.stopPropagation) evt.stopPropagation();
  if (!subsection) return;
  if (
    !(await showInAppConfirm(
      "All fields for this policy will be permanently deleted.",
      { title: "Delete Policy", confirmLabel: "Delete", variant: "danger" },
    ))
  )
    return;
  try {
    const wasLife = /^life(_|$)/i.test(String(subsection || "").trim());
    const out = await api("/api/insurance-policy/delete", {
      method: "POST",
      body: JSON.stringify({ subsection }),
    });
    dirty.clear();
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = wasLife ? "annuity_death_benefits" : "estate";
    renderMain();
    showMessage(out.message || "Policy deleted. Save Changes when ready.");
  } catch (e) {
    showMessage("Error deleting policy: " + e.message, "error");
  }
}
