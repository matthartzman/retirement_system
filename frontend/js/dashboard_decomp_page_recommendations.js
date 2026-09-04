// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function recRowValue(row) {
  return row
    ? String(displayValueForInput(row, valOf(row)) || valOf(row) || "").trim()
    : "";
}

export function recStepRows(stepId) {
  try {
    return rowsForStep(stepId, { includeInactive: true }) || [];
  } catch (_e) {
    return [];
  }
}

export function recFindStepRow(stepId, labels) {
  const wanted = (Array.isArray(labels) ? labels : [labels]).map(norm);
  return (
    recStepRows(stepId).find((r) => wanted.includes(norm(r.label))) ||
    rows.find((r) => isEditable(r) && wanted.includes(norm(r.label))) ||
    null
  );
}

export function recFindBy(sectionName, subsectionName, labelName) {
  return (
    rows.find(
      (r) =>
        isEditable(r) &&
        String(r.section || "") === sectionName &&
        norm(r.subsection) === norm(subsectionName) &&
        norm(r.label) === norm(labelName),
    ) || null
  );
}

export function recYes(row) {
  const v = String(valOf(row) || "")
    .trim()
    .toLowerCase();
  return ["yes", "true", "1", "on", "enabled"].includes(v);
}

export function revealAndFocus(el) {
  if (!el) return false;
  let node = el.parentElement;
  while (node) {
    if (node.tagName === "DETAILS" && !node.open) node.open = true;
    // Collapsible nav/section groups use a class rather than <details>.
    if (node.classList && node.classList.contains("collapsed"))
      node.classList.remove("collapsed");
    node = node.parentElement;
  }
  if (el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "center" });
  if (el.focus) el.focus({ preventScroll: true });
  if (el.select) el.select();
  return true;
}

export function jumpRecommendationSource(stepId, rowIndex) {
  if (rowIndex !== undefined && rowIndex !== null && rowIndex !== "")
    inactiveEditReveals.add(Number(rowIndex));
  // #269: reset a merged workspace (e.g. spending_core) to its default
  // sub-tab -- a stale localStorage tab choice made setStep() below land on
  // the right page but the target field wasn't rendered, so "Review growth
  // mode" looked like it did nothing but scroll to top.
  const _tabs = (typeof STRATEGY_TABS !== "undefined" && STRATEGY_TABS[stepId]) || null;
  if (_tabs && _tabs.length) {
    try {
      localStorage.setItem(strategyTabKey(stepId), _tabs[0]);
    } catch (_e) {}
  }
  setStep(stepId || activeStep);
  setTimeout(() => {
    let el = null;
    if (rowIndex !== undefined && rowIndex !== null && rowIndex !== "")
      el =
        document.querySelector(`[data-row="${rowIndex}"]`) ||
        document.getElementById("field-" + rowIndex);
    revealAndFocus(el);
  }, 80);
}

export function recommendationSourceButton(item) {
  const row = item.row;
  if (!row)
    return `<button class="btn tiny" type="button" data-step-id="${esc(item.stepId || activeStep)}">${esc(item.actionLabel || "Open page")}</button>`;
  return `<button class="btn tiny recommendation-source-jump" type="button" onclick="jumpRecommendationSource('${escJs(item.stepId || activeStep)}',${Number(row.row_index)})">${esc(item.actionLabel || "Review input")}</button>`;
}

export function rothPageRecommendations() {
  const recs = [];
  const policy = recFindStepRow("roth_conversion", "roth_conversion_policy");
  const policyVal = String(policy ? valOf(policy) : "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  const targetBracket = recFindStepRow("roth_conversion", [
    "roth_target_bracket_rate",
    "roth_conversion_target_bracket_base_year",
  ]);
  const irmaa = recFindStepRow("roth_conversion", "irmaa_guardrail_mode");
  const irmaaVal = String(irmaa ? valOf(irmaa) : "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  const headroom = recFindStepRow("roth_conversion", "roth_headroom_usage_pct");
  const headroomPct = headroom ? parsePercentInput(valOf(headroom)) : 0;
  const fixed = recFindStepRow("roth_conversion", "roth_fixed_annual_amount");
  const fixedAmt = fixed ? fieldNumericValue(fixed) : 0;
  const end = recFindStepRow("roth_conversion", [
    "roth_conv_window_end_offset",
    "conversion_window_end_offset",
    "max_conversion_years",
  ]);
  if (!policy || !policyVal) {
    recAdd(
      recs,
      "warn",
      "Choose a Roth conversion policy",
      "A missing policy leaves the workbook without a clear voluntary-conversion strategy. Pick none, bracket-fill, IRMAA-guarded, fixed-dollar, or optimizer mode intentionally.",
      policy || targetBracket,
      "roth_conversion",
      "Changes current taxes, future RMDs, Medicare thresholds, survivor tax compression, and after-tax inheritance.",
      "Choose policy",
    );
  } else if (
    ["none", "off", "disabled", "no_voluntary_conversions"].includes(policyVal)
  ) {
    recAdd(
      recs,
      "info",
      "Run one bounded Roth comparison",
      "The current policy disables voluntary conversions. Keep that as the base case, but compare one bracket-fill or IRMAA-guarded build before ruling conversions out.",
      policy,
      "roth_conversion",
      "May raise current taxes while lowering lifetime taxes, RMDs, and survivor tax risk.",
      "Review policy",
    );
  } else if (
    irmaa &&
    ["ignore", "off", "none", "warn_only"].includes(irmaaVal)
  ) {
    recAdd(
      recs,
      "warn",
      "Add a hard Medicare IRMAA guardrail for final review",
      "The active Roth policy can generate useful tax savings, but warn-only/ignored IRMAA behavior may let conversions cross Medicare premium cliffs. Use an avoidance mode for an advisor-ready comparison.",
      irmaa,
      "roth_conversion",
      "Affects conversion size, Medicare premiums, lifetime tax, and cash-flow headroom.",
      "Review guardrail",
    );
  } else {
    recAdd(
      recs,
      "info",
      "Keep Roth tests bounded by a clear ceiling",
      `Policy ${recRowValue(policy)} is active. Confirm the bracket or IRMAA ceiling reflects the highest current-tax cost the household is willing to accept.`,
      targetBracket || irmaa || policy,
      "roth_conversion",
      "Keeps tax savings, terminal net worth, and Medicare-premium tradeoffs explainable.",
      "Review ceiling",
    );
  }
  if (
    headroom &&
    headroomPct >= 100 &&
    policyVal &&
    !["none", "off", "disabled", "no_voluntary_conversions"].includes(policyVal)
  ) {
    recAdd(
      recs,
      "info",
      "Consider leaving threshold headroom",
      "Headroom is set to 100%, which uses the full available bracket/IRMAA room. For final plans, a 90–95% guardrail can reduce accidental cliff exposure from dividends, interest, or data updates.",
      headroom,
      "roth_conversion",
      "Reduces risk of crossing a tax or Medicare threshold because of small income-estimate changes.",
      "Review headroom",
    );
  }
  if (fixed && fixedAmt > 0 && end && String(valOf(end) || "").trim() === "") {
    recAdd(
      recs,
      "warn",
      "Set a fixed-conversion window",
      "Fixed-dollar conversions are active but the window/end control appears blank. Define when conversions stop so the recommendation does not persist longer than intended.",
      end,
      "roth_conversion",
      "Changes the years where current taxes rise and future RMDs fall.",
      "Review window",
    );
  }
  return recs.slice(0, 4);
}

export function allocationPageRecommendations(stepId) {
  const recs = [];
  const mode = allocationSelectionMode();
  const modeRow = allocationModeRow();
  if (mode === "user_target") {
    const total = allocationTargetTotalPct();
    if (Math.abs(total - 100) > 0.01) {
      recAdd(
        recs,
        "warn",
        "Balance active targets to 100%",
        "User-specified allocation is active, but included/alternate target rows total " +
          total.toFixed(2) +
          "%. Rebalance the target table before saving or building.",
        allocationTargetRows()[0] || modeRow,
        "allocation_assets",
        "Prevents misleading drift, expected-return, and Monte Carlo comparisons.",
        "Review targets",
      );
    } else {
      recAdd(
        recs,
        "info",
        "Compare the optimizer before finalizing the user target",
        "User-specified allocation is valid. Use the optimizer as a second opinion before locking the target mix for a final report.",
        modeRow,
        "allocation_assets",
        "Tests whether risk tolerance, glide path, human capital, and concentrated assets imply a different mix.",
        "Review mode",
      );
    }
  } else {
    if (optimizerOverrideHasEntries() && !optimizerOverrideValid()) {
      recAdd(
        recs,
        "warn",
        "Fix optimizer override total",
        "Optimizer override rows are partly filled but total " +
          optimizerOverrideTotalPct().toFixed(2) +
          "%. Complete them to 100% or clear all override cells to use the computed recommendation.",
        optimizerOverrideRows()[0] || modeRow,
        "allocation_assets",
        "Avoids accidentally replacing the optimizer with an invalid override.",
        "Review overrides",
      );
    } else {
      recAdd(
        recs,
        "info",
        "Document why the optimizer target is acceptable",
        "Optimizer mode is active. Confirm the supporting risk, glide path, capital-market preset, and concentration assumptions before relying on the computed target.",
        modeRow,
        "allocation_assets",
        "Makes allocation recommendations easier to defend in Build Impact and reports.",
        "Review allocation mode",
      );
    }
  }
  const cash = findTargetRow("Cash");
  if (cash && parsePercentInput(valOf(cash)) < 2 && mode === "user_target") {
    recAdd(
      recs,
      "info",
      "Check whether cash target supports the reserve floor",
      "Cash target is below 2%. Confirm separate cash-reserve rules are enough before reducing liquid ballast.",
      cash,
      "allocation_assets",
      "Can affect liquidity failures, rebalancing pressure, and downside comfort.",
      "Review cash target",
    );
  }
  const risk = recFindBy("Model Constants", "Allocation", "risk_tolerance");
  const glide = recFindBy("Model Constants", "Allocation", "glide_path");
  if (stepId === "allocation_policy" && risk) {
    recAdd(
      recs,
      "info",
      "Keep risk tolerance and glide path paired",
      "Risk tolerance should match the glide path used near retirement. Review both together when a plan is close to the retirement date.",
      risk,
      "allocation_policy",
      "Controls the optimizer recommendation and can affect Monte Carlo success and terminal value.",
      "Review risk input",
    );
  }
  if (stepId === "allocation_policy" && glide) {
    recAdd(
      recs,
      "info",
      "Confirm the glide path before final reports",
      "A glide path can de-risk over time; a static target keeps risk more constant. Choose deliberately before comparing stress results.",
      glide,
      "allocation_policy",
      "Changes age-based allocation and long-horizon risk/reward.",
      "Review glide path",
    );
  }
  return recs.slice(0, 4);
}

export function spendingPageRecommendations() {
  const recs = [];
  const base = recFindStepRow("spending_core", "annual_spending_base_year");
  const growth = recFindStepRow("spending_core", "core_spending_growth_mode");
  const manual = recFindStepRow(
    "spending_core",
    "core_spending_manual_growth_rate",
  );
  const freeze = recFindStepRow("spending_core", "spending_freeze_year");
  const inflation = recFindStepRow("spending_core", "inflation_general");
  const baseAmt = base ? fieldNumericValue(base) : 0;
  if (!base || baseAmt <= 0) {
    recAdd(
      recs,
      "warn",
      "Enter a realistic core spending base",
      "Core spending is blank or zero, so the projection cannot reliably estimate withdrawals, taxes, or plan risk. Use Spending Analysis or budget lines to seed it.",
      base || growth,
      "spending_core",
      "Spending is usually one of the largest drivers of terminal net worth and probability of success.",
      "Review spending base",
    );
  } else {
    recAdd(
      recs,
      "info",
      "Reconcile core spending with actuals before building",
      "Core spending is " +
        fmtMoney(baseAmt) +
        ". Compare it with recent transactions and budget lines before treating a report as final.",
      base,
      "spending_core",
      "Aligns the 30-year model with real household behavior and reduces false precision.",
      "Review spending base",
    );
  }
  if (growth && norm(valOf(growth)) === "manual_override") {
    const manualPct = manual ? parsePercentInput(valOf(manual)) : 0;
    const cpi = inflation ? parsePercentInput(valOf(inflation)) : NaN;
    if (Number.isFinite(cpi) && manualPct > cpi + 1) {
      recAdd(
        recs,
        "warn",
        "Explain why spending grows faster than CPI",
        "Manual spending growth is more than one point above general inflation. That may be intentional, but it should be documented before final review.",
        manual,
        "spending_core",
        "Raises withdrawals, taxes, and Monte Carlo failure risk over the retirement horizon.",
        "Review growth rate",
      );
    } else {
      recAdd(
        recs,
        "info",
        "Document the manual spending-growth assumption",
        "Manual spending growth overrides CPI. Add notes or confirm the rate so future comparisons are interpretable.",
        manual || growth,
        "spending_core",
        "Changes long-term spending, withdrawals, and terminal net worth.",
        "Review growth mode",
      );
    }
  } else if (growth) {
    recAdd(
      recs,
      "info",
      "Use a scenario for non-CPI spending stress",
      "Core spending currently follows CPI/general inflation. For pressure testing, keep the base case stable and use Scenarios for a higher-spending case.",
      growth,
      "spending_core",
      "Keeps base-plan spending clean while still testing lifestyle risk.",
      "Review growth mode",
    );
  }
  if (freeze && fieldNumericValue(freeze) > 0) {
    recAdd(
      recs,
      "info",
      "Confirm the spending freeze year is intentional",
      "A spending freeze can improve long-term results materially. Confirm it represents real lifestyle behavior, not a placeholder.",
      freeze,
      "spending_core",
      "Can raise terminal net worth and success probability by stopping inflation growth after the freeze year.",
      "Review freeze year",
    );
  }
  return recs.slice(0, 4);
}

export function socialSecurityPageRecommendations() {
  const recs = [];
  // claim_age is legacy (superseded by claim_date -- see schema.csv) and no
  // longer rendered on this page, so linking a recommendation to it would
  // send the user to a field they can't find. Read claim_date rows instead
  // and derive the age the same way the compact table's own badge does --
  // that also keeps this recommendation correct once a user has entered a
  // claim_date, instead of judging by a claim_age value that stopped
  // updating the moment claim_date took over.
  const claimDateRows = recStepRows("income_retirement").filter(
    (r) => norm(r.label) === "claim_date",
  );
  const claims = claimDateRows.map((r) => ({
    row: r,
    age: ssClaimAgeFromDate(r.subsection, r),
  }));
  const survivor =
    recFindBy(
      "Social Security",
      "Policy",
      "survivor_benefit_uses_deceased_claim_age",
    ) ||
    recFindBy("Social Security", "Policy", "survivor_pct_of_higher_benefit");
  const earlyMatch = claims.find((c) => c.age > 0 && c.age < 67);
  const not70Match = claims.find((c) => c.age >= 67 && c.age < 70);
  const early = earlyMatch ? earlyMatch.row : null;
  const not70 = not70Match ? not70Match.row : null;
  if (early) {
    recAdd(
      recs,
      "warn",
      "Stress-test early claiming",
      "At least one claim age is before full retirement age. Compare a later-claim scenario before finalizing because early claiming can permanently reduce survivor income.",
      early,
      "income_retirement",
      "Affects annual income, Roth conversion room, taxes, withdrawals, survivor benefits, and terminal value.",
      "Review claim age",
    );
  } else if (not70) {
    recAdd(
      recs,
      "info",
      "Compare delaying the higher earner to 70",
      "A claim age is between full retirement age and 70. Test delaying the higher benefit to age 70, especially when survivor protection matters.",
      not70,
      "income_retirement",
      "May improve longevity and survivor income but can increase bridge withdrawals before claiming.",
      "Review claim age",
    );
  } else if (claims.length) {
    recAdd(
      recs,
      "info",
      "Document why age-70 claiming is acceptable",
      "Claim ages appear set to 70. Confirm the bridge years are affordable and the Roth window before Social Security is intentional.",
      claims[0],
      "income_retirement",
      "Delaying benefits can improve inflation-linked income and survivor protection.",
      "Review claim age",
    );
  }
  if (
    survivor &&
    !recYes(survivor) &&
    norm(survivor.label).includes("survivor_benefit_uses")
  ) {
    recAdd(
      recs,
      "warn",
      "Review survivor benefit treatment",
      "Survivor benefit handling affects the income floor for the surviving member. Confirm this setting before relying on survivor stress outputs.",
      survivor,
      "income_retirement",
      "Changes survivor cash flow, withdrawals, taxes, and downside risk.",
      "Review survivor setting",
    );
  }
  return recs.slice(0, 4);
}

export function pageRecommendationsForStep(stepId) {
  if (!RECOMMENDATION_STEP_IDS.has(stepId) || !planLoaded) return [];
  try {
    if (stepId === "roth_conversion") return rothPageRecommendations();
    if (stepId === "allocation_assets" || stepId === "allocation_policy")
      return allocationPageRecommendations(stepId);
    if (stepId === "spending_core") return spendingPageRecommendations();
    if (stepId === "income_retirement")
      return socialSecurityPageRecommendations();
    return [];
  } catch (e) {
    return [
      {
        level: "warn",
        title: "Recommendations unavailable",
        body: "The page-local recommendation engine could not interpret the current values on this page. Save and reload, then review the source fields manually.",
        stepId,
        row: null,
        impact: String((e && e.message) || e),
        actionLabel: "Open page",
      },
    ];
  }
}

export function pageRecommendationsHtml(stepId) {
  const items = pageRecommendationsForStep(stepId);
  if (!items.length) return "";
  const rowsHtml = items
    .map(
      (item) =>
        `<div class="recommendation-card ${esc(item.level || "info")}"><div><span class="recommendation-level">${esc(item.level || "info")}</span><h4>${esc(item.title)}</h4><p>${esc(formatAcronyms(item.body))}</p>${item.impact ? `<p class="small"><b>Why it matters:</b> ${esc(formatAcronyms(item.impact))}</p>` : ""}</div><div class="recommendation-actions">${recommendationSourceButton(item)}</div></div>`,
    )
    .join("");
  return `<details class="page-recommendations" data-contract="${RECOMMENDATION_ENGINE_VERSION}"><summary class="page-recommendations-head"><span class="eyebrow">Page recommendations</span><h3>Suggested reviews before the next build (${items.length})</h3><p class="small">Explainable suggestions only — nothing is changed automatically. Each item links back to the input that controls the recommendation.</p></summary><div class="page-recommendation-list">${rowsHtml}</div></details>`;
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  recRowValue,
  recStepRows,
  recFindStepRow,
  recFindBy,
  recYes,
  revealAndFocus,
  jumpRecommendationSource,
  recommendationSourceButton,
  rothPageRecommendations,
  allocationPageRecommendations,
  spendingPageRecommendations,
  socialSecurityPageRecommendations,
  pageRecommendationsForStep,
  pageRecommendationsHtml,
});
