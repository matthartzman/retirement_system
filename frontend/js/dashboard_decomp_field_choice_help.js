// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function helpList(items) {
  const clean = (items || []).filter((x) => String(x || "").trim());
  if (!clean.length) return "";
  return `<ul>${clean.map((x) => `<li>${x}</li>`).join("")}</ul>`;
}

export function filterChoiceOptionsForRow(r, opts) {
  const label = String(r?.label || "").trim();
  if (
    activeStep === "annuity_death_benefits" &&
    r?.section === "Insurance In Force" &&
    norm(label) === "policy_type"
  ) {
    return (opts || []).filter((x) => norm(choiceValue(x)) === "life");
  }
  if (
    activeStep === "estate" &&
    r?.section === "Insurance In Force" &&
    norm(label) === "policy_type"
  ) {
    return (opts || []).filter(
      (x) =>
        !["life", "auto", "home", "property_and_casualty"].includes(
          norm(choiceValue(x)),
        ),
    );
  }
  return opts || [];
}

export function choiceOptions(r) {
  const label = String(r?.label || "").trim();
  const type = String(r?.schema?.type || "").toLowerCase();
  const units = String(r?.units || "");
  const fixed = {
    filing_status: ["MFJ", "Single", "HOH", "MFS"], survivor_filing_status: ["Single", "HOH", "MFS"],
    state: _stateNameChoiceOptions(), residence_state: _stateNameChoiceOptions(), target_state: _stateAbbrChoiceOptions(),
    roth_conversion_policy: [
      "optimize_terminal_tax",
      "fill_to_bracket",
      "fill_to_irmaa",
      "fixed_dollar",
      "none",
    ],
    core_spending_growth_mode: [
      { value: "cpi", label: "Use CPI / General Inflation" },
      { value: "manual_override", label: "Manual spending increase override" },
    ],
    roth_bracket_strategy: [
      "NONE",
      "FILL_CURRENT_BRACKET",
      "FILL_TARGET_BRACKET",
      "PARTIAL_TARGET_BRACKET",
      "IRMAA_GUARDED",
      "SURVIVOR_TAX_AWARE",
      "RMD_REDUCTION",
      "LEGACY_TARGETED",
      "OPTIMIZER_CHOOSES",
      "FIXED_DOLLAR",
      "PHASE_VARYING",
    ],
    roth_objective_mode: [
      "BALANCED_RETIREMENT",
      "MINIMIZE_LIFETIME_TAX",
      "MAXIMIZE_TERMINAL_NET_WORTH",
      "LEGACY_OPTIMIZED",
      "ESTATE_TAX_AWARE",
      "CUSTOM_WEIGHTED",
    ],
    estate_tax_objective_mode: ["OFF", "MONITOR_ONLY", "BALANCED", "STRONG"],
    irmaa_guardrail_mode: [
      "IGNORE",
      "WARN_ONLY",
      "AVOID_NEXT_TIER",
      "AVOID_TIER_2_OR_ABOVE",
      "CUSTOM_MAGI_CAP",
    ],
    legacy_objective_mode: ["OFF", "LOW", "BALANCED", "STRONG"],
    mc_engine_mode: [
      {
        value: "quick_vectorized",
        label: "Simple — Quick Vectorized (faster, approximate)",
      },
      {
        value: "advanced_exact_scalar",
        label: "Complex — Advanced Exact Scalar (slower, advisor-ready)",
      },
    ],
    city_type: ["urban", "suburban", "rural"],
    type: ["purchase", "rent"],
    allocation_selection_mode: [
      { value: "user_target", label: "Use user-specified allocation" },
      { value: "optimizer_recommendation", label: "Use allocation optimizer recommendation" },
      { value: "max_sharpe", label: "Best risk-adjusted mix within your risk limits (max-Sharpe, risk-budgeted)" },
      { value: "tangency", label: "Best risk-adjusted mix with no risk limits applied (max-Sharpe, pure tangency)" },
      { value: "real_loss_aware", label: "Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation" },
    ],
    capital_market_assumption_horizon_source: [
      { value: "manual", label: "Manual (use the horizon selected above)" },
      { value: "auto_from_withdrawals", label: "Auto-derive from projected withdrawals" },
    ],
    selection_action: ["include", "exclude", "consider_alternate_first"],
  };
  if (Array.isArray(r?.choice_options) && r.choice_options.length)
    return filterChoiceOptionsForRow(r, r.choice_options);
  if (fixed[label]) return filterChoiceOptionsForRow(r, fixed[label]);
  if (type !== "choice" && norm(units) !== "choice") return [];
  const text = [r?.schema?.description || "", r?.notes || "", units].join(" ");
  let candidate = text.split(";")[0];
  if (!candidate.includes("|")) candidate = text;
  let opts = candidate
    .split("|")
    .map((x) => x.trim())
    .filter((x) => x && x.length < 120 && !/[.]/.test(x))
    .filter(
      (x, i, a) =>
        a.findIndex(
          (y) =>
            norm(typeof y === "object" ? y.value : y) ===
            norm(typeof x === "object" ? x.value : x),
        ) === i,
    );
  return filterChoiceOptionsForRow(r, opts);
}

export function choiceLabel(o) {
  return typeof o === "object" ? String(o.label ?? o.value ?? "") : String(o);
}

export function yesNoOptionHelp(row) {
  const label = humanLabel(row.label, row).toLowerCase();
  return [
    `<b>YES</b>: include, enable, or assume this ${esc(label)} applies in the plan.`,
    `<b>NO</b>: exclude, disable, or assume this ${esc(label)} does not apply.`,
  ];
}

export function choiceHelpText(row, opt) {
  const v = norm(choiceValue(opt)),
    l = norm(row.label);
  const display = esc(formatAcronyms(choiceLabel(opt).replace(/_/g, " ")));
  const maps = {
    user_target:
      "Use the editable user target percentages as the allocation recommendation.",
    optimizer_recommendation:
      "Let the optimizer choose the allocation using risk, return, volatility, correlation, and constraints.",
    include: "Allow this asset class or setting to be used directly.",
    exclude: "Do not recommend this asset class or setting.",
    consider_alternate_first:
      "Credit an existing asset or income source before recommending new exposure.",
    cpi: "Increase spending with the general inflation assumption.",
    manual_override: "Use the manual growth rate instead of CPI.",
    quick_vectorized:
      "Faster directional Monte Carlo approximation for drafts and diagnostics.",
    advanced_exact_scalar:
      "Slower advisor-ready Monte Carlo using the full projection path.",
    ignore: "Do not constrain the recommendation for this threshold.",
    warn_only: "Allow the action but flag the threshold crossing.",
    avoid_next_tier: "Stop or reduce the action before the next IRMAA tier.",
    avoid_tier_2_or_above:
      "Avoid larger Medicare premium jumps, not just the first tier.",
    custom_magi_cap: "Use a manually entered MAGI ceiling.",
    off: "Turn this objective or module off.",
    monitor_only:
      "Calculate and show exposure without materially steering the recommendation.",
    balanced: "Use this objective as one part of the recommendation score.",
    strong: "Give this objective more influence in scoring.",
    none: "Do not use this strategy or objective.",
    fixed_dollar:
      "Use the entered fixed-dollar amount instead of letting the model size it.",
  };
  return `<b>${display}</b>: ${esc(maps[v] || "Select this when it best matches the real-world assumption or planning objective for this field.")}`;
}

export function fieldAllowedValues(row) {
  const units = String(row.units || "").trim();
  const type = String(row.schema?.type || "").toLowerCase();
  const boolish =
    type === "boolean" ||
    /^(yes\/no|true\/false)$/i.test(units) ||
    /^(YES|NO|TRUE|FALSE)$/i.test(valOf(row));
  if (boolish) return helpList(yesNoOptionHelp(row));
  const opts = choiceOptions(row);
  if (opts && opts.length)
    return helpList(opts.map((o) => choiceHelpText(row, o)));
  const kind = valueKind(row);
  if (isDateField(row))
    return "<p>Use a calendar date. Consistent dates allow the model to place the value in the right tax year, age year, or cash-flow year.</p>";
  if (kind === "currency")
    return "<p>Enter dollars. Higher dollar amounts usually increase the item being modeled; whether that helps or hurts depends on whether the field is an asset, income, tax, liability, contribution, or expense.</p>";
  if (kind === "percent")
    return "<p>Enter a percentage. For rates, higher values usually amplify the related growth, tax, return, inflation, allocation, or guardrail effect.</p>";
  if (kind === "number")
    return "<p>Enter a number, age, year, count, or ranking as described by the label. Whole-number fields should generally not include decimals.</p>";
  if (units) return `<p>Expected format: ${esc(formatAcronyms(units))}.</p>`;
  return "<p>Use the value that best matches the documented fact, current estimate, or scenario assumption. When unsure, open nearby related fields before changing it.</p>";
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  helpList,
  filterChoiceOptionsForRow,
  choiceOptions,
  choiceLabel,
  yesNoOptionHelp,
  choiceHelpText,
  fieldAllowedValues,
});
