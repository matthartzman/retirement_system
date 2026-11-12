// ── Field rendering (fieldHtml, value kinds, edit begin/finish, field groups) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005); the save-validation Set/Map ride along. Bridge below.
export function toIsoDateValue(value) {
  const v = String(value || "").trim();
  if (!v) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  let m = v.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/);
  if (m) {
    return `${m[1].padStart(4, "0")}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  }
  m = v.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
  if (m) {
    let y = m[3];
    if (y.length === 2) y = (Number(y) > 40 ? "19" : "20") + y;
    return `${y.padStart(4, "0")}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
  }
  if (/^\d{4}$/.test(v)) return `${v}-01-01`;
  return v;
}

export function isDateField(r) {
  const l = norm(r.label);
  return (
    (l.includes("dob") || l.includes("date")) &&
    !l.includes("year") &&
    !l.includes("end_year")
  );
}

export function currencyRaw(value) {
  const n = numberFromDisplay(value);
  return n === null ? String(value ?? "").trim() : decimalTrim(String(n));
}

export function budgetMoneyInputValue(value) {
  if (value === undefined || value === null || String(value).trim() === "")
    return "";
  return currencyDisplay(value);
}

export function focusBudgetMoney(el) {
  if (el) el.value = currencyRaw(el.value);
}

export function blurBudgetMoney(el) {
  if (el) el.value = budgetMoneyInputValue(el.value);
  if (taxBudgetChanged) renderMain();
}

export function budgetMoneyNumber(value) {
  const n = numberFromDisplay(value);
  return n === null ? 0 : n;
}

export function valueKind(r) {
  const units = String(r?.units || "");
  const u = norm(units);
  const l = norm(r?.label);
  const type = String(r?.schema?.type || "").toLowerCase();
  if (r && norm(r.label) === "down_payment") return "percent";
  if (r && l === "heloc_repayment_years") return "number";
  if (r && l === "tlh_transaction_cost_bps") return "number";
  // exclusion_ratio is stored as a raw 0-1 fraction (0.738), unlike every
  // other percent field in this app (stored already on a 0-100 scale, e.g.
  // "5.00%") -- it needs its own kind so display/storage can scale by 100
  // instead of just appending "%". Must be checked before the generic
  // "exclusion" dollar-keyword match below, which would otherwise catch it
  // (that keyword is for genuine dollar exclusions like
  // section_121_exclusion_mfj and annual_exclusion_per_donee).
  if (r && l === "exclusion_ratio") return "percent_fraction";
  // Every *_weight setting (Roth optimizer and legacy weights, real-loss
  // weight) is stored as a raw multiplier (0.35, 1.00) and shown as a percent
  // (35%, 100%). Checked before the keyword matching below, which reads a
  // "tax" in the label as a dollar amount.
  if (r && /_weight$/.test(l)) return "percent_fraction";
  if (
    !r ||
    isDateField(r) ||
    ["boolean", "choice", "secret", "path"].includes(type)
  )
    return "plain";
  if (/^(yes\/no|true\/false)$/i.test(units)) return "plain";
  if (["percent", "pct", "percentage"].includes(type)) return "percent";
  if (["dollars", "currency", "usd", "money"].includes(type)) return "currency";
  if (["year", "integer", "int", "number", "numeric"].includes(type))
    return "number";
  if (
    units.includes("%") ||
    u.includes("pct") ||
    u.includes("percent") ||
    l.endsWith("pct") ||
    l.includes("percentage") ||
    l.includes("rate") ||
    l.includes("return") ||
    l.includes("volatility") ||
    l.includes("correlation") ||
    l.includes("inflation") ||
    l.includes("cola")
  )
    return "percent";
  if (l.endsWith("_year")) return "number";
  if (u === "years" || u === "year" || u === "age") return "number";
  if (
    units.includes("$") ||
    u.includes("usd") ||
    u.includes("dollar") ||
    u.includes("money") ||
    hasAny(l, [
      "amount",
      "balance",
      "value",
      "price",
      "cost",
      "basis",
      "proceeds",
      "spending",
      "income",
      "salary",
      "bonus",
      "rent",
      "payment",
      "mortgage",
      "premium",
      "benefit",
      "contribution",
      "expense",
      "asset",
      "liability",
      "equity",
      "face_amount",
      "funding",
      "transfer",
      "taxable_income",
      "taxes",
      "tax",
      "exclusion",
      "sale_price",
      "purchase_price",
      "gross_sell",
      "net_sell",
      "capital_gain",
      "ltcg",
      "fmv",
      "fair_market_value",
      "market_value",
      "cashflow",
      "cash_flow",
      "insurance",
      "utilities",
    ])
  )
    return "currency";
  return "plain";
}

export function choiceValue(o) {
  return typeof o === "object" ? String(o.value ?? o.label ?? "") : String(o);
}

export function storageValueForInput(row, value) {
  if (row && isDateField(row)) return toIsoDateValue(value);
  const kind = valueKind(row);
  if (kind === "currency") return currencyRaw(value);
  if (kind === "percent") return percentRaw(value);
  if (kind === "percent_fraction") {
    const n = numberFromDisplay(value);
    return n === null ? String(value ?? "").trim() : decimalTrim(String(n / 100));
  }
  if (kind === "number")
    return decimalTrim(
      String(numberFromDisplay(value) ?? String(value ?? "").trim()),
    );
  return String(value ?? "");
}

export function displayValueForInput(row, value) {
  if (row && isDateField(row)) return toIsoDateValue(value);
  // Some account-reference fields (e.g. home_sale_proceeds_account) are
  // schema-typed as currency/number even though their stored value is a
  // person/account token like "Member_2_Trust" — translate those before
  // falling into numeric formatting, which would otherwise blank them out.
  if (PERSON_VALUE_TOKEN_RE.test(String(value ?? "").trim()))
    return translatePersonValueLabel(value);
  const kind = valueKind(row);
  if (kind === "currency") return currencyDisplay(value);
  if (kind === "percent")
    return percentDisplay(value, percentDisplayDecimals(row, value));
  if (kind === "percent_fraction") {
    const n = numberFromDisplay(value);
    if (n === null) return String(value ?? "");
    const scaled = n * 100;
    // percentDisplayDecimals reads decimal-place counts straight off the raw
    // text (row.value etc.), which is correct for a normal percent field but
    // would misfire here: the *stored* fraction "0.738" has 3 decimal
    // digits, while the *scaled* "73.8" needs only 1 -- ×100 shifts the
    // decimal point left by 2. Subtract that shift from each source's raw
    // decimal count instead of reusing percentDisplayDecimals directly.
    const fractionDecimals = (text) => {
      const m = String(text ?? "").match(/\.(\d+)/);
      return m ? Math.max(0, Math.min(6, m[1].length - 2)) : 0;
    };
    const decimals = Math.max(
      fractionDecimals(value),
      fractionDecimals(row?.value),
      fractionDecimals(row?.schema?.default),
    );
    return percentDisplay(scaled, decimals);
  }
  if (kind === "number")
    return formatNumberValue(
      value,
      numberDisplayDecimals(row, value),
      numberDisplayDecimals(row, value),
    );
  return translatePersonValueLabel(value);
}

export function beginEdit(idx, el) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row) return;
  showFieldHelp(idx);
  if (
    el &&
    el.tagName &&
    el.tagName.toLowerCase() === "input" &&
    !isDateField(row)
  ) {
    el.value = storageValueForInput(row, valOf(row));
  }
}

export function finishEdit(idx, el) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row || !el) return;
  const stored = storageValueForInput(row, el.value);
  editValue(idx, stored, el);
  if (el.tagName && el.tagName.toLowerCase() === "input" && !isDateField(row)) {
    el.value = displayValueForInput(row, stored);
  }
}

// UX-003 (WI-504): row_index values the backend's save validation rejected
// on the last failed save. fieldHtml marks those controls aria-invalid; the
// set is replaced on every failed save and cleared on a successful one.
export const saveValidationInvalidRows = new Set();
// WI-020 / UX-004: the server's message for each rejected row (row_index -> text), shown
// under the control (aria-describedby) and listed, with links, in the #saveErrorSummary region.
export const saveValidationErrors = new Map();
export function saveFieldErrorId(rowIndex) {
  return "field-" + rowIndex + "-err";
}
export function saveFieldErrorHtml(rowIndex) {
  return (
    '<div class="field-error" id="' +
    saveFieldErrorId(rowIndex) +
    '"><span aria-hidden="true">&#9888; </span><span class="sr-only">Error: </span>' +
    esc(saveValidationErrors.get(rowIndex) || "") +
    "</div>"
  );
}

// UX-002 (system review 2026-09-25, WI-503): stable ids tying each plan-data
// control to its visible label and its describing text (unit caption,
// Required badge, inactive-value note), so assistive tech announces the
// field name, required state and help rather than "edit text"/"YES".
export function fieldControlId(rowIndex) {
  return "field-" + rowIndex + "-ctl";
}

export function fieldHtml(r, opts) {
  const hideUnit = !!(opts && opts.hideUnit);
  const value = valOf(r);
  const missing = isMissing(r);
  const dirtyHere = dirty.has(r.row_index);
  const units = String(r.units || "").trim();
  const type = (r.schema?.type || "text").toLowerCase();
  const lblNorm = norm(r.label);
  const boolish =
    type === "boolean" ||
    /^(yes\/no|true\/false)$/i.test(units) ||
    /^(YES|NO|TRUE|FALSE)$/i.test(value);
  const ctlId = fieldControlId(r.row_index);
  const lblId = "field-" + r.row_index + "-lbl";
  const unitId = "field-" + r.row_index + "-unit";
  const reqId = "field-" + r.row_index + "-req";
  const inactiveId = "field-" + r.row_index + "-inactive";
  const inactiveState = rowBuildUsageState(r, activeStep);
  const inactiveRevealed =
    inactiveEditReveals.has(r.row_index) && !inactiveState.active;
  const saveErr = saveValidationErrors.has(r.row_index);
  const errId = saveFieldErrorId(r.row_index);
  const describedBy = [
    saveErr ? errId : "",
    missing ? reqId : "",
    units && !hideUnit ? unitId : "",
    inactiveRevealed ? inactiveId : "",
  ].filter(Boolean);
  const invalid = missing || saveValidationInvalidRows.has(r.row_index);
  // Shared by every control branch below. Checkboxes additionally get
  // aria-labelledby: they sit inside the .toggle-switch <label>, whose own
  // YES/NO text would otherwise become their accessible name.
  const a11y =
    ` id="${ctlId}"` +
    (describedBy.length ? ` aria-describedby="${describedBy.join(" ")}"` : "") +
    (isRequired(r) ? ' aria-required="true"' : "") +
    (invalid ? ' aria-invalid="true"' : "");
  let control = "";
  if (
    lblNorm === "allocation_selection_mode" ||
    lblNorm === "allocation_mode"
  ) {
    const mode = allocationSelectionMode();
    control = `<select${a11y} data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);renderMain()" onfocus="showFieldHelp(${r.row_index})"><option value="user_target" ${mode === "user_target" ? "selected" : ""}>Use user-specified allocation</option><option value="optimizer_recommendation" ${mode === "optimizer_recommendation" ? "selected" : ""}>Use allocation optimizer recommendation</option><option value="max_sharpe" ${mode === "max_sharpe" ? "selected" : ""}>Best risk-adjusted mix, staying within the risk limits you set (max-Sharpe)</option><option value="tangency" ${mode === "tangency" ? "selected" : ""}>Best risk-adjusted mix, ignoring your risk limits (tangency)</option><option value="real_loss_aware" ${mode === "real_loss_aware" ? "selected" : ""}>Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation</option></select>`;
  } else if (boolish) {
    const yes =
      String(value).toUpperCase() === "YES" ||
      String(value).toUpperCase() === "TRUE";
    control = `<label class="toggle-switch" data-row="${r.row_index}"><input type="checkbox"${a11y} aria-labelledby="${lblId}" ${yes ? "checked" : ""} onchange="editValue(${r.row_index},this.checked?'YES':'NO',this)" onfocus="showFieldHelp(${r.row_index})"><span class="toggle-track" aria-hidden="true"></span><span class="toggle-text toggle-text-yes" aria-hidden="true">YES</span><span class="toggle-text toggle-text-no" aria-hidden="true">NO</span></label>`;
  } else if (type === "choice" || norm(units) === "choice" || window.STATE_INPUT_LABELS.has(lblNorm)) {
    const opts = choiceOptions(r);
    if (opts.length) {
      const cur = String(value || "").trim();
      const rerender =
        lblNorm === "core_spending_growth_mode" ||
        lblNorm === "roth_conversion_policy" ||
        lblNorm === "irmaa_guardrail_mode" ||
        lblNorm === "hsa_withdrawal_mode";
      control = `<select${a11y} data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);${rerender ? "renderMain()" : ""}" onfocus="showFieldHelp(${r.row_index})">${opts
        .map((o) => {
          const ov = choiceValue(o),
            ol = choiceLabel(o);
          return `<option value="${esc(ov)}" ${norm(ov) === norm(cur) ? "selected" : ""}>${esc(translatePersonPlaceholders(formatAcronyms(ol.replace(/_/g, " "))))}</option>`;
        })
        .join("")}</select>`;
    } else {
      // #<housing focus loss>: a stable data-focus-key lets ticket 285's
      // captureMainPaneFocus/restoreMainPaneFocus revive this exact input
      // (and its caret) if something -- e.g. a Housing row's reestimate
      // ripple -- calls renderMain() synchronously while it's focused.
      control = `<input type="text"${a11y} data-row="${r.row_index}" data-focus-key="field:${r.row_index}" value="${esc(String(value || ""))}" placeholder="${esc(r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
    }
  } else {
    const inputType = isDateField(r) ? "date" : "text";
    const inputValue = displayValueForInput(r, value);
    control = `<input type="${inputType}"${a11y} data-row="${r.row_index}" data-focus-key="field:${r.row_index}" value="${esc(inputValue)}" placeholder="${esc(r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
  }
  const note = formatAcronyms(r.schema?.description || r.notes || "");
  const req = missing
    ? `<span class="badge req" id="${reqId}">Required</span>`
    : "";
  const inactiveBadge = inactiveRevealed
    ? '<span class="badge warn">Inactive unless activated</span>'
    : "";
  // hideUnit: some callers (e.g. the Next Housing Step editor) render their
  // own compact hint and opt out of this raw type-token caption.
  const unit = units && !hideUnit
    ? `<div class="unit" id="${unitId}">${esc(formatAcronyms(units))}</div>`
    : "";
  const kind = valueKind(r);
  const negClass = kind === "currency" ? moneyNegativeClass(value) : "";
  // U2: currency, date, and dependency-linked (mode/policy/enabling) fields stay
  // full-width — pairing them beside an unrelated field raises mis-entry and
  // mislabeling risk for exactly the fields where getting it wrong matters most.
  const paired =
    kind !== "currency" && !isDateField(r) && dependencyRank(r.label) > "01";
  // Gating fields (mode/policy/enabled) keep the full row so the settings they
  // control read as subordinate to them. Everything else — including currency
  // and dates, which U2 previously pinned full-width — now flows into the
  // column grid, since the control is sized to its value and the label stays
  // inside the same bordered card.
  const sizeClass = fieldSizeClass(r);
  const flow = dependencyRank(r.label) > "01" && sizeClass !== "w-long";
  const saveErrHtml = saveErr ? saveFieldErrorHtml(r.row_index) : "";
  return `<div class="field ${missing ? "missing" : ""} ${saveErr ? "invalid" : ""} ${dirtyHere ? "dirty" : ""} ${inactiveRevealed ? "inactive-edit" : ""}${paired ? " paired" : ""}${flow ? " flow" : ""}${sizeClass ? " " + sizeClass : ""}${negClass}" id="field-${r.row_index}" onclick="showFieldHelp(${r.row_index})"><div><div class="field-label"><label id="${lblId}"${boolish ? "" : ` for="${ctlId}"`}>${esc(opts && opts.dropRoth ? humanLabel(r.label, r).replace(/^Roth\s+/i, "") : humanLabel(r.label, r))}${fieldLabelNoteHtml(r)}</label>${fieldTooltipHtml(lblNorm, r)}</div><div class="field-meta">${req}${dirtyHere ? '<span class="badge dirty">Edited</span>' : ""}${inactiveBadge}</div></div><div>${control}${saveErrHtml}${unit}${inactiveRevealed ? `<div class="unit" id="${inactiveId}">${esc(formatAcronyms(inactiveState.activation || "Change this value or its controlling setting to make it active in the build."))}</div>` : ""}</div></div>`;
}

export function sortRowsByDependency(rs) {
  return (rs || []).slice().sort((a, b) => {
    const ka = dependencyRank(a.label) + norm(a.label),
      kb = dependencyRank(b.label) + norm(b.label);
    return ka.localeCompare(kb);
  });
}

export function renderFieldGroups(rs) {
  if (!rs.length)
    return '<div class="field-list"><p>No fields in this step.</p></div>';
  const groups = [];
  sortRowsByDependency(rs).forEach((r) => {
    const g = friendlyGroup(r);
    let group = groups.find((x) => x.name === g);
    if (!group) {
      group = { name: g, rows: [] };
      groups.push(group);
    }
    group.rows.push(r);
  });
  const many = (rs.length > 14 || groups.length > 3) && groups.length > 1;
  let html = "";
  groups.forEach((g) => {
    const body = sortRowsByDependency(g.rows).map(fieldHtml).join("");
    if (many && g.rows.length > 1) {
      html += `<details><summary>${esc(g.name)}</summary><div class="field-list">${body}</div></details>`;
    } else {
      html += `<div class="field-list">${groups.length > 1 ? `<h3 class="group-title">${esc(g.name)}</h3>` : ""}${body}</div>`;
    }
  });
  return html;
}
Object.assign(window, {
  beginEdit, blurBudgetMoney, budgetMoneyInputValue, budgetMoneyNumber, choiceValue, currencyRaw,
  displayValueForInput, fieldControlId, fieldHtml, finishEdit, focusBudgetMoney, isDateField,
  renderFieldGroups, saveFieldErrorHtml, saveFieldErrorId, saveValidationErrors,
  saveValidationInvalidRows, sortRowsByDependency, storageValueForInput, toIsoDateValue, valueKind,
});
