// ── Field guidance and help panel (fieldGuidance, showFieldHelp) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005). Bridge below.
export function fieldGuidance(row) {
  const l = norm(row.label),
    s = norm(row.section),
    sub = norm(row.subsection);
  if (FIELD_GUIDANCE_OVERRIDES[l]) return FIELD_GUIDANCE_OVERRIDES[l];
  if (l === "net_monthly_payment")
    return {
      purpose: "The monthly amount that actually lands in your bank account from this pension or annuity, after the payer withholds income tax. Withholding = gross payment minus this amount.",
      impact: "None on the projection: the plan taxes the gross payment itself and shows taxes separately. This is kept so you can match the plan to your bank deposits.",
      consider: "Copy the net (after-withholding) amount from the payer's statement or your bank deposit. Leave blank if nothing is withheld; net is then the same as gross.",
    };
  if (l === "annuity_pv_discount_rate")
    return {
      purpose: "Net worth counts your annuities and pension as the present value of their remaining payments. This is the rate used to discount those future payments back to today. Leave it blank to use your portfolio return.",
      impact: "A lower rate gives your guaranteed income a higher value today, raising net worth (and the estate-tax estimate the Roth conversion planner uses). It does not change the payments or your cash flow.",
      consider: "Guaranteed income is usually valued like a high-quality bond, so 4-5% is common. Your portfolio return is higher and values the same payments lower.",
    };
  let purpose = fieldDefaultMeaning(row);
  let impact =
    "This can affect user-facing results such as annual cash flow, terminal net worth, lifetime taxes, post-terminal estate taxes, Medicare premiums, probability of success, downside risk, or workbook recommendations.";
  let consider =
    "Ask: is this a documented fact, a best estimate, or a scenario lever? If better information supports a higher value, raise it; if the current value is overstated, outdated, or intentionally being stress-tested lower, reduce it.";
  if (l.includes("dob")) {
    purpose = "Sets a person's age for the plan.";
    impact =
      "Affects retirement age, life expectancy horizon, Social Security timing, RMD timing, healthcare years, and tax filing phases.";
    consider =
      "Use the actual birth date. If privacy is a concern in a demo, use a realistic placeholder age.";
  } else if (l.includes("filing_status")) {
    purpose = "Defines the tax filing assumption.";
    impact =
      "Affects federal tax brackets, NIIT thresholds, deductions, and survivor tax modeling.";
    consider =
      "Use the current filing status; update after marriage, divorce, or widowhood.";
  } else if (l.includes("state")) {
    purpose = "Sets the resident state for tax and planning assumptions.";
    impact = "Affects state tax lookup and report labeling.";
    consider =
      "Use the state expected for the modeled retirement period, or update when relocation plans change.";
  } else if (l.includes("retirement")) {
    purpose = "Defines when work income or savings behavior changes.";
    impact =
      "Affects income, payroll tax, contributions, withdrawals, healthcare bridge costs, and Monte Carlo timing.";
    consider =
      "Use the best current target date; test alternatives as scenarios.";
  } else if (
    l.includes("spending") ||
    l.includes("expense") ||
    l.includes("vacation") ||
    l.includes("travel") ||
    l.includes("wedding") ||
    l.includes("home_project")
  ) {
    purpose =
      "Defines planned spending the portfolio or income sources must support.";
    impact =
      "Usually one of the largest drivers of projected cash-flow shortfalls, terminal net worth, Monte Carlo success, and stress-test narratives in the workbook.";
    consider =
      "Use Large Discretionary Expenses for flexible items such as vacations, weddings, home projects, gifts, vehicle purchases, and family support.";
  } else if (
    l.includes("social_security") ||
    l === "ss" ||
    l.includes("pension") ||
    l.includes("annuity")
  ) {
    purpose = "Captures recurring retirement income.";
    impact =
      "Reduces required portfolio withdrawals and may count as fixed-income-like coverage when enabled.";
    consider =
      "Use conservative values and note whether the amount is inflation-adjusted.";
  } else if (
    l.startsWith("h_qcd_") ||
    l.startsWith("w_qcd_") ||
    l === "h_qcd_annual_amount" ||
    l === "w_qcd_annual_amount"
  ) {
    // #219/#220: per-member QCD (Qualified Charitable Distribution) amount/
    // start/end fields all share the same underlying concept -- one shared
    // explanation instead of six near-duplicate FIELD_GUIDANCE_OVERRIDES entries.
    if (l.includes("start_year")) {
      purpose =
        "QCDs (Qualified Charitable Distributions) let an IRA owner age 70½+ send money straight from their IRA to charity, tax-free. This optional override sets the first plan year this member's QCD giving begins.";
      impact =
        "Leaving this blank starts QCD giving automatically the year this member turns 70½-eligible. Setting a later year delays when the tax-free giving (and any RMD credit it provides) begins.";
      consider =
        "Only fill this in if giving should start later than 70½-eligibility (e.g. charitable giving isn't planned until a later year); otherwise leave it blank.";
    } else if (l.includes("end_year")) {
      purpose =
        "QCDs (Qualified Charitable Distributions) let an IRA owner age 70½+ send money straight from their IRA to charity, tax-free. This optional override sets the last plan year this member's QCD giving applies.";
      impact =
        "Leaving this blank continues QCD giving through the end of the plan. Setting an earlier year stops the tax-free giving (and its RMD credit) after that year, reverting to normal taxable withdrawals for any remaining RMD.";
      consider =
        "Only fill this in if QCD giving should stop before the plan ends (e.g. a giving plan with a defined end date); otherwise leave it blank.";
    } else {
      purpose =
        "QCDs (Qualified Charitable Distributions) let an IRA owner age 70½+ send money straight from their own IRA to charity, excluded from taxable income entirely. This is the annual dollar amount this member gives this way, capped at that year's own RMD and the statutory per-person QCD limit.";
      impact =
        "This amount is excluded from Adjusted Gross Income and can count toward satisfying this member's own Required Minimum Distribution for the year — typically lowering taxable income, Medicare IRMAA exposure, and NIIT exposure more than an equivalent itemized charitable deduction would.";
      consider =
        "Set this to the amount this member actually plans to give from IRA assets each year once 70½-eligible; leave at $0 if this member's charitable giving isn't coming from IRA assets.";
    }
  } else if (l.includes("mortgage") || l.includes("real_estate_taxes")) {
    purpose =
      "Captures home debt, mortgage payments, or real-estate tax cash flow.";
    impact =
      "Affects net worth, cash-flow needs, tax deductions, and retirement spending pressure.";
    consider =
      "Update balance, rate, payment, real-estate tax amount, annual RE tax adjustment, and payoff timing annually.";
  } else if (l.includes("expected_return")) {
    purpose =
      "Sets the long-term return assumption for this asset class in the allocation optimizer.";
    impact =
      "Higher values make the optimizer more willing to recommend the class; lower values reduce its appeal.";
    consider =
      "Use long-term capital-market assumptions, not recent performance. Pair with volatility and correlation.";
  } else if (l.includes("volatility")) {
    purpose = "Sets the risk level for this asset class.";
    impact =
      "Higher volatility makes an asset class less attractive unless return or diversification benefits offset the risk.";
    consider =
      "Volatility should reflect downside experience over the selected horizon.";
  } else if (
    l.includes("allocation_selection_mode") ||
    l === "allocation_mode"
  ) {
    purpose = "Chooses which allocation target the workbook uses.";
    impact =
      "user_target applies the editable target_pct rows; optimizer_recommendation and max_sharpe are risk-tolerance-driven model recommendations; tangency is an unconstrained max-Sharpe reference; real_loss_aware blends a per-holding-period-bucket solve based on this household's own projected withdrawal schedule.";
    consider =
      "Review the recommendation rationale (shown below once selected) and compare it with the user target mix. Keep user target_pct rows totaling 100% even when a computed mode is selected.";
  } else if (l === "holding_period_allocation_enabled") {
    // #219: layman-quality example the user provided verbatim (lightly
    // split across purpose/impact/consider) -- the standard to match for
    // every non-intuitive field, not just this one.
    purpose =
      "It's an opt-in setting (off by default) that changes how the tool's asset-allocation recommendation is built — but only for the \"optimizer recommendation\" and \"max Sharpe\" modes; it does nothing if you're using a manually-set target allocation. The idea it's based on: there's a well-known chart showing that whether cash or stocks are \"safer\" depends on how long you're holding. Cash is safe if you need the money next year, but risky if you sit on it for 20 years (inflation quietly eats it). Stocks are the opposite — risky short-term, but historically the safer bet over long stretches once you account for inflation.";
    impact =
      "What flipping it on actually does: the tool already knows, from your own retirement projection, roughly when each dollar in your portfolio will actually get spent (it simulates your future withdrawals year by year). With this setting on, it uses that withdrawal timeline to sort your money into \"buckets\" by how soon it's needed — money needed in the next 0–2 years vs. money that won't be touched for 16+ years — and then nudges the recommended allocation: money you'll need soon gets nudged toward more cash (safety for near-term spending); money you won't touch for a long time gets nudged toward more stocks/growth investments (since historically it's the safer place for money over long horizons). It also shifts the bond portion toward shorter-duration bonds instead of long ones, since the underlying data shows long bonds don't buy you much extra safety. Guardrail: it only ever raises these amounts — it won't push you into less cash or less stock than your existing risk-tolerance settings already call for. A separate \"strength\" dial (0–100%) lets you turn the effect up or down without switching it off entirely.";
    consider =
      "Bottom line: it makes the recommended allocation a little more personalized to your actual spending schedule, rather than one generic risk-tolerance number applied to your whole portfolio. Selecting allocation_selection_mode=real_loss_aware enables the same withdrawal-schedule discovery automatically, so this toggle is mainly for nudging the existing optimizer/max-Sharpe modes rather than switching to that dedicated mode.";
  } else if (l === "holding_period_floor_strength") {
    purpose =
      "Dials how strongly the holding-period floors (above) are applied.";
    impact =
      "100% applies the full near-term-Cash / long-horizon-growth floor; 0% disables the floor's effect without turning holding_period_allocation_enabled off.";
    consider = "Only has an effect while holding_period_allocation_enabled is on.";
  } else if (
    l === "real_loss_aware_risk_aversion" ||
    l === "real_loss_aware_weight"
  ) {
    purpose =
      "Tunes the per-holding-period-bucket solve used by the real_loss_aware allocation mode.";
    impact =
      l === "real_loss_aware_risk_aversion"
        ? "Higher values penalize variance more heavily within each bucket's solve (same scale as the optimizer's own internal risk aversion)."
        : "Higher values weight each bucket's real-loss-probability penalty more heavily relative to variance and expected return.";
    consider =
      "Only has an effect while allocation_selection_mode is real_loss_aware.";
  } else if (l === "capital_market_assumption_horizon_source") {
    purpose =
      "Chooses how the capital-market planning horizon (above) is determined.";
    impact =
      "manual uses the horizon selected above as-is; auto_from_withdrawals derives the effective horizon from this household's own projected withdrawal schedule instead.";
    consider =
      "Affects every allocation mode's expected-return/volatility assumptions, not just real_loss_aware.";
  } else if (l === "optimizer_override_pct") {
    purpose =
      "Optional manual override for the optimizer recommendation for this asset class.";
    impact =
      "When optimizer mode is selected and any override is entered, the optimizer override percentages replace the computed optimizer target. The override total must equal 100%.";
    consider =
      "Leave all optimizer override rows blank to use the computed optimizer recommendation. Use Copy optimizer override to user-defined when you want these edits to overwrite the user-defined allocation.";
  } else if (l.includes("target_pct")) {
    purpose = "Sets the user-specified target percentage for this asset class.";
    impact =
      "Affects allocation recommendations, drift analysis, and ETF idea guidance when allocation mode is user-specified. All user target_pct rows must total 100%.";
    consider =
      "Start with the default mix in the comment, then adjust with advisor review. Cash is included as its own class.";
  } else if (l.includes("maximum_target")) {
    purpose = "Caps how much the optimizer can allocate to the class.";
    impact =
      "Controls concentration and prevents the optimizer from overusing a high-return or low-risk assumption.";
    consider =
      "Set tighter caps for illiquid, specialized, or hard-to-access asset classes.";
  } else if (l === "selection_action") {
    purpose = "Sets the compact asset-class selection policy.";
    impact =
      "Include allows target exposure, Exclude prevents new recommendation exposure, and Consider alternate first counts the selected existing asset/source toward this class before recommending new exposure.";
    consider =
      "Use Consider alternate first when another plan asset should satisfy the role before this asset class is recommended directly.";
  } else if (l === "alternate_asset_class") {
    purpose =
      "Selects the existing asset or non-liquid source used when the row is set to Consider alternate first.";
    impact =
      "The chosen source is credited against this class before recommending new exposure.";
    consider =
      "Choose an existing asset that reasonably satisfies the same portfolio role, such as pension income toward bonds or home equity toward real estate.";
  } else if (l.includes("pricing_mode") || s.includes("market_pricing")) {
    purpose = "Controls how the system prices holdings.";
    impact = "Affects account totals, allocation, drift, and diagnostics.";
    consider =
      "CACHE is usually best for normal use; LIVE is best for testing; OFFLINE avoids external calls. Cost basis is now a last-resort estimate only when there is no cached quote.";
  } else if (l.includes("sehi")) {
    purpose =
      "Captures SEHI — self-employed health insurance — treatment for S-Corp or self-employed income.";
    impact =
      "Affects adjusted gross income, above-the-line deductions, payroll/W-2 presentation, QBI calculations, and income tax projections.";
    consider =
      "For S-Corp owners, SEHI is commonly included in W-2 Box 1 and then deducted on Schedule 1 when eligibility rules are met. Confirm with the tax preparer.";
  } else if (l.includes("ss_funding_discount")) {
    purpose =
      "Models a Social Security funding shortfall haircut from the configured year onward.";
    impact =
      "Reduces gross Social Security income in the projection, which can lower taxable income, portfolio withdrawals, survivor income, and workbook cash-flow schedules.";
    consider =
      "Ask: do you want to model the current-law funding risk, a no-haircut optimistic case, or a harsher stress? Use 0% for no funding cut; use a higher percentage or earlier year for a more conservative Social Security stress.";
  } else if (l.includes("roth") || sub.includes("roth_conversion")) {
    purpose = "Controls how Roth conversions are sized or scored.";
    impact =
      "Affects the Roth Conversion sheet, current taxable income, future RMD pressure, Medicare IRMAA exposure, survivor tax compression, Roth legacy value, estate-tax-aware strategy ranking, and Executive Summary explanation.";
    consider =
      "Ask: is the goal lower lifetime taxes, higher terminal net worth, survivor protection, or legacy value? A tax-focused answer points to bracket/tax controls; a beneficiary or survivor answer points to Legacy and survivor scoring; a Medicare-premium answer points to IRMAA guardrails.";
  } else if (l.includes("irmaa") || sub.includes("irmaa")) {
    purpose =
      "Controls the Medicare premium threshold guardrail used by Roth conversion and tax planning.";
    impact =
      "Affects the Roth Conversion schedule, projected MAGI, Medicare premium warnings, and any workbook explanation of why conversions stop in a year.";
    consider =
      "Ask: would crossing an IRMAA tier be acceptable for this household? If avoiding Medicare premium jumps matters, use an avoidance guardrail and leave headroom; if tax savings are more important than premium cliffs, loosen or warn-only the guardrail.";
  } else if (l.includes("estate_tax_objective")) {
    purpose =
      "Controls whether estate-tax exposure affects Roth strategy scoring.";
    impact =
      "When active, the optimizer penalizes strategies that increase projected federal or state estate tax; if no estate tax is projected, the impact should be zero.";
    consider =
      "Default Balanced keeps estate awareness active without inventing an estate-tax cost. State estate tax is included only when the selected state rules create projected exposure.";
  } else if (l === "mc_engine_mode") {
    purpose = "Chooses the Monte Carlo engine for this build.";
    impact =
      "Advanced Exact Scalar gives the most realistic probability of success and downside-risk results because every simulated path uses the full projection logic. Quick Vectorized is faster but approximate, so it is best for quick diagnostics and UI testing.";
    consider =
      "Ask: am I experimenting or producing final guidance? Choose Quick Vectorized when you need a fast directional answer; choose Advanced Exact Scalar when the result will be used for recommendations, client review, or final decisions.";
  } else if (l.includes("monte_carlo") || s.includes("monte_carlo")) {
    purpose =
      "Controls how the plan tests uncertainty rather than one fixed projection path.";
    impact =
      "Affects probability of success, downside terminal net worth, liquidity-floor failures, risk ranges, sensitivity grids, and build time.";
    consider =
      "Ask: is build speed or statistical confidence more important right now? Lower counts or Quick mode speed up drafts; higher counts and Advanced mode are better when the success rate will influence a recommendation.";
  } else if (s.includes("annuity_death_benefits")) {
    purpose = "Sets the death benefit payable for a specific policy and year.";
    impact = "Affects estate, survivor, and legacy benefit reporting by year.";
    consider =
      "Enter the value shown on the policy schedule. If a benefit is no longer available in a year, enter 0.";
  }
  return {
    purpose: formatAcronyms(purpose),
    impact: formatAcronyms(impact),
    consider: formatAcronyms(consider),
  };
}

export function ensureHelpPanelVisible() {
  document.body.classList.add("help-open");
}

export function showFieldHelp(idx) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row) return;
  // Contextual help Phase 1: with help_registry.js loaded, field help follows focus without
  // opening the panel; explicit openers ("i", aria-controls="helpPanel") open it there.
  if (window.RPHelp) window.RPHelp.pinned("field", idx);
  else ensureHelpPanelVisible();
  const label = humanLabel(row.label, row);
  const note = translatePersonPlaceholders(
    formatAcronyms(row.schema?.description || row.notes || ""),
  );
  const g = { ...fieldGuidance(row), ...(window.RPHelp?.fieldEntry(row.label) || {}) };
  const meaning = formatAcronyms(
    g.purpose || note || `${label} is an input used by the planner.`,
  );
  const options = fieldAllowedValues(row);
  const connections = formatAcronyms(fieldConnection(row));
  const impact = formatAcronyms(fieldLikelyImpact(row, g));
  const acronyms = acronymDefinitionsHtml([
    label,
    note,
    meaning,
    connections,
    impact,
    row.units,
  ]);
  const sourceNote =
    note &&
    ![meaning, impact, connections].some((x) => String(x || "").includes(note))
      ? `<h3>Source note</h3><p>${esc(note)}</p>`
      : "";
  const required = isMissing(row)
    ? `<div class="help-callout">This required field still needs a value before the plan is complete.</div>`
    : "";
  document.getElementById("helpPanel").innerHTML =
    `<div class="help-title">${esc(label)}</div><div class="help-body"><h3>What this value means</h3><p>${esc(meaning)}</p><h3>Value options and how to choose</h3>${options}<h3>How it relates to this page</h3><p>${connections}</p><h3>Likely impact of changing it</h3><p>${esc(impact)}</p>${sourceNote}${acronyms}${required}</div>`;
}
Object.assign(window, {
  ensureHelpPanelVisible, fieldGuidance, showFieldHelp,
});
