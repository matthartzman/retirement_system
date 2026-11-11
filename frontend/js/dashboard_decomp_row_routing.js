// ── Row routing and build-usage state (rawRowsForStep, module gates, rowBuildUsageState) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005); moduleTaxonomy is read through planModuleTaxonomy().

// #323: the three Strategy screens (strategy_optimize/strategy_stress/
// strategy_scenarios) are STEPS entries with no case of their own below --
// every plan row still routes to the legacy shell id it always did (that
// switch is deliberately untouched; row routing for the Find a Field, the
// build change summary, and every source-jump button in the app all key off
// the shell ids directly, see spec S1). Without this aggregation,
// rawRowsForStep() falls through the switch's `default: return false` for
// the three new ids and returns [] forever, which makes stepStats() report
// zero required/zero missing for them permanently -- and since the Strategy
// nav group's readiness badge sums stepStats(id).missing over every step in
// the group, that badge would silently and permanently read zero, the one
// nav group in the app with no readiness signal at all.
//
// planning_levers and planning_workbench have no case below and own no rows
// -- both are derived/computed pages, not editable input pages -- so they
// are correctly absent here, not an oversight.
const STRATEGY_SCREEN_MEMBER_STEPS = {
  strategy_optimize: [
    "allocation_assets",
    "allocation_policy",
    // #338 W-C (C4): the Spending workspace's Withdrawal Order tab is gone;
    // its rows render on Optimize's HSA Drawdown / Withdrawal Sequencing /
    // Harvesting sections and are counted here.
    "withdrawal_strategy",
    // #329/#330 W9: heloc_strategy moved to its own nav step (W13 put it in
    // Housing & Property) -- see STEPS in dashboard.js. It keeps returning
    // its own rows unaggregated (via rawRowsForStep("heloc_strategy")
    // directly); it is simply no longer one of Optimize's member steps.
    // #330 P8 / Q6 (W13): roth_conversion and entity_charitable left the
    // same way, for the Taxes group. Each is its own nav step with its own
    // readiness badge now, so aggregating them into Optimize's would
    // double-count them across two visible nav entries.
  ],
  strategy_stress: [
    "monte_carlo_options",
    "survivor_stress",
    "ltc_stress",
    "divorce_options",
  ],
  strategy_scenarios: ["scenarios"],
  strategy_workbench: [],
};

export function rawRowsForStep(id) {
  const members = STRATEGY_SCREEN_MEMBER_STEPS[id];
  if (members) {
    // Union rather than replacement: each member id must keep returning its
    // own rows unaggregated (tested directly), since every other surface in
    // the app still keys off them. Deduped by row_index as a defensive
    // measure -- the member lists are disjoint today, but a future addition
    // that overlaps another must not silently inflate stepStats() totals.
    const seen = new Set();
    const out = [];
    for (const memberId of members) {
      for (const r of rawRowsForStep(memberId)) {
        if (!seen.has(r.row_index)) {
          seen.add(r.row_index);
          out.push(r);
        }
      }
    }
    return out;
  }
  return rows.filter(isEditable).filter((r) => {
    const lbl = norm(r.label),
      sub = norm(r.subsection),
      sec = r.section;
    switch (id) {
      case "household_people":
        return (
          sec === "Household" &&
          hasAny(r.label, [
            "name",
            "dob",
            "state",
            "filing_status",
            "retirement",
            "mortality",
            "survivor",
          ])
        );
      case "retirement_wellness":
        return rowIsRetirementWellness(r);
      case "income_work":
        return (
          (sec === "Cashflow" &&
            ((sub === "earned_income" &&
              [
                "annual_earned_income",
                "earned_income_start_year",
                "earned_income_annual_increase",
                "entity_type",
                "ytd_remainder_earned_income_override",
              ].includes(lbl)) ||
              sub === "self_employment" ||
              sub === "s_corp" ||
              sub === "retirement_contributions")) ||
          sec === "Payroll Tax" ||
          // #239: moved here from Economic & Tax Assumptions' Retirement
          // section (its own section is "Model Constants", not "Cashflow" --
          // grouped under "Retirement Contributions" via friendlyGroup
          // regardless of its actual "Retirement" subsection).
          lbl === "rollover_401k_year"
        );
      case "income_retirement":
        return sec === "Income Streams" || sec === "Social Security";
      case "spending_core":
        return (
          (sec === "Cashflow" &&
            sub === "spending" &&
            lbl !== "daf_annual_contribution" &&
            lbl !== "annual_spending_base_year") ||
          (sec === "Economic Assumptions" &&
            sub === "" &&
            lbl === "inflation_general") ||
          (sec === "Model Constants" &&
            sub === "retirement" &&
            lbl === "spending_freeze_year") ||
          // #338 W-C: Housing costs and Wellness are edited in Spending
          // Model's accordions, so sourceStepForRow() lands there.
          rowIsSpendingSourceRow(r)
        );
      case "spending_travel_extras":
        return false;
      case "spending_mortgage_events":
        return (
          (sec === "Cashflow" && sub === "mortgage") ||
          (sec === "Other Assets" && sub === "home") ||
          (sec === "Model Constants" && sub === "home_sale") ||
          (sec === "Housing" &&
            [
              "current_home",
              "next_step_1",
              "next_step_2",
              "home_improvements",
            ].includes(sub))
        );
      case "assets_home_cash":
        return sec === "Other Assets" && sub === "cash";
      case "assets_special":
        return (
          (sec === "Other Assets" && sub.startsWith("other_asset")) ||
          (sec === "HSA Policy" && sub !== "window") ||
          [
            "Education Funding",
            "Equity Compensation",
            "Note Receivable",
            "Hybrid LTC",
          ].includes(sec)
        );
      // #330 P8 / Q6 (W13): the Family & Business nav group's page. The
      // catalog declares these two sections as csv_sections of
      // education_funding_529 and equity_compensation (domain FAMILY_
      // BUSINESS), which is where the membership comes from -- it is not a
      // second hand-kept list. This is ADDITIVE: the rows keep their home on
      // assets_special above, and BUILD_IMPACT_SOURCE_STEP_IDS deliberately
      // does not list family_business, so sourceStepForRow() still answers
      // "Other Assets & Debts" for every one of them and no other
      // surface sees the new step at all.
      case "family_business":
        return ["Education Funding", "Equity Compensation"].includes(sec);
      // Cash pair-status floor inputs. Roth Basis and the switch live only here; the HSA expense bank is a second way in
      // (its home stays on assets_special, which sourceStepForRow() reaches first).
      case "account_tax_basis":
        return (
          sec === "Roth Basis" ||
          (sec === "Cashflow" && sub === "cash_tracking" && lbl === "cash_pair_status_tax") ||
          (sec === "HSA Policy" && lbl === "hsa_expense_bank")
        );
      case "estate":
        return sec === "Estate Planning" || sec === "Account Titling";
      case "annuity_death_benefits":
        return (
          sec === "Annuity Death Benefits" ||
          sec === "Insurance In Force" ||
          // #323: the live auto-insurance baseline (data_io.py's fallback
          // Auto Ins. Delta source when no Auto policy exists) belongs beside
          // the Auto policies it falls back from, not on State Residency.
          (sec === "State Comparison" &&
            sub === "auto_insurance" &&
            lbl === "current_state_baseline_annual")
        );
      case "allocation_policy":
        return (
          (sec === "Model Constants" && sub === "allocation") ||
          (sec === "Asset Class Assumptions" && sub === "global")
        );
      case "allocation_assets":
        return (
          (sec === "Asset Allocation Policy" &&
            sub === "global" &&
            [
              "allocation_selection_mode",
              "allocation_mode",
              "use_allocation_optimizer",
              "holding_period_allocation_enabled",
              "holding_period_floor_strength",
              "real_loss_aware_risk_aversion",
              "real_loss_aware_weight",
            ].includes(lbl)) ||
          (sec === "Asset Allocation Policy" &&
            sub !== "global" &&
            lbl === "target_pct") ||
          (sec === "Asset Class Optimizer Controls" &&
            [
              "selection_action",
              "alternate_asset_class",
              "optimizer_override_pct",
            ].includes(lbl))
        );
      case "capital_market":
        return false;
      case "market_pricing":
        return false;
      case "economic_tax_assumptions":
        return (
          !rowIsHomeSaleAssumption(r) &&
          ((sec === "Economic Assumptions" &&
            // reinvest_dividends_default lives on the Sales Ledger's cash panel;
            // cash_yield_rate is back here (the rate cash earns is an economic assumption).
            // #236: annuity_default_dividend_rate/annuity_default_additional_income_pct
            // moved to SS, Pensions & Annuities' "Plan-wide income stream settings".
            ![
              "reinvest_dividends_default",
              "annuity_default_dividend_rate",
              "annuity_default_additional_income_pct",
              "annuity_pv_discount_rate",
              // #358: these live in the Tax Assumptions table now
              // (dashboard_decomp_tax_assumptions.js); tax_model_baseline is a
              // system-written record, not an input.
              "tax_model_baseline",
              "fed_tax_bracket_inflator",
              "state_income_tax_rate",
              "tax_law_scenario",
              "higher_rates_start_year",
            ].includes(lbl)) ||
            sec === "Account Policy" ||
            // #238/#237: Payroll Tax / Medicare and / Self-Employment (FICA
            // rates) already live on Work Income (sec === "Payroll Tax" is
            // unconditional there) -- were also showing here, the same
            // editable fields in two places.
            (sec === "Payroll Tax" &&
              !["medicare", "self_employment"].includes(sub)) ||
            (sec === "Wellness" && !rowIsRetirementWellness(r)) ||
            (sec === "Model Constants" &&
              ["retirement", "capital_gains"].includes(sub) &&
              // #239: rollover_401k_year moved to Work Income; RMD start ages
              // moved to the Household & People table.
              ![
                "spending_freeze_year",
                "rollover_401k_year",
                "member_1_rmd_start_age",
                "member_2_rmd_start_age",
              ].includes(lbl)))
        );
      case "scenarios":
        return (
          (sec === "Scenarios" && !rowIsDivorceScenario(r)) ||
          (sec === "Model Constants" && sub === "home_sale") ||
          (sec === "Other Assets" &&
            sub === "home" &&
            (lbl.startsWith("home_sale_") ||
              lbl === "home_basis" ||
              homeValueLabelIsCanonical(r.label)))
        );
      case "monte_carlo_options":
        return (
          rowIsMonteCarlo(r) || hasAny(r.label, ["monte_carlo", "simulation"])
        );
      case "divorce_options":
        return rowIsDivorceScenario(r);
      case "state_residency":
        // #323: current_state_baseline_annual moved to the Insurance page's
        // annuity_death_benefits step above; every other State Comparison row
        // stays here.
        return (
          sec === "State Comparison" &&
          !(sub === "auto_insurance" && lbl === "current_state_baseline_annual")
        );
      case "heloc_strategy":
        // Ticket 340: the enable switch itself now lives on Plan Features
        // (see dashboard_decomp_plan_features.js's HELOC special-case in
        // planFlagRowHtml), not on this page -- it would otherwise render
        // twice.
        return sec === "HELOC" && lbl !== "heloc_enabled";
      case "entity_charitable":
        // The DAF/QCD enable switches live on Plan Features only.
        return (
          (sec === "DAF" && lbl !== "enabled") ||
          (sec === "Cashflow" &&
            sub === "charitable_giving" &&
            lbl !== "qcd_enabled")
        );
      case "survivor_stress":
        return (
          sec === "Household" && hasAny(r.label, ["survivor", "mortality"])
        );
      case "ltc_stress":
        return sec === "Hybrid LTC";
      case "withdrawal_strategy":
        return sec === "Withdrawal Policy" && sub !== "roth_conversion";
      case "optional_functions":
        return sec === "Optional Functions";
      case "roth_conversion":
        return (
          (sec === "Withdrawal Policy" &&
            sub === "roth_conversion" &&
            lbl !== "roth_irmaa_cap") ||
          (sec === "Model Constants" && sub === "roth_conversion")
        );
      case "all_assumptions":
        return true;
      case "assumption_signoff":
        return false;
      case "review":
        return false;
      default:
        return false;
    }
  });
}

export function fieldNumericValue(row) {
  const raw = String(valOf(row) || "").replace(/[$,%\s,]/g, "");
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

export function rowModuleGate(section) {
  return (moduleGates.section_gates || {})[section] || null;
}

// #330 §3.4 (W5): the reverse-direction warning on an optional module's
// switch. `degrades_without` is declared on the module that shows less, but
// the question a user actually has is at the switch they are about to flip:
// "what do I lose if I turn this off?" The server serves both directions
// (config_service._module_taxonomy), so this reads the answer rather than
// inverting the relation here — a second copy of the relation in JS is
// exactly the hand-maintained twin #329 exists to end.
//

// Returns "" when nothing degrades without `key`, which is most modules, so
// the caller can concatenate unconditionally.
// `taxonomy` is a parameter with a default rather than a closed-over read so
// the function stays pure and directly testable: a module-scoped `let` is a
// lexical binding, invisible to the vm-sandbox loader the frontend tests use.
export function moduleOffImpactWarning(key, taxonomy = planModuleTaxonomy()) {
  const mod = ((taxonomy || {}).modules || {})[key];
  const hit = (mod && mod.degraded_by) || [];
  if (!hit.length) return "";
  // "the fan chart from Charts", joined into a list that reads as English:
  // "A", "A and B", "A, B and C".
  const parts = hit.map((d) => `${d.loses} from ${d.name}`);
  const listed =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return `Turning ${(mod.name || key)} off also removes ${listed}.`;
}

export function rowBuildUsageState(row, stepId = "") {
  if (!row) return { active: true };
  const optional = optionalModuleState(row);
  if (optional) return optional;
  const l = norm(row.label),
    s = String(row.section || ""),
    sub = norm(row.subsection || "");
  if (
    s === "Social Security" &&
    l === "monthly_pia_at_fra_today_dollars" &&
    fieldNumericValue(row) <= 0
  )
    return {
      active: false,
      reason:
        "Monthly at FRA/PIA is blank or zero, so the build uses the age-67 (Full Retirement Age) entry from this person's benefit table instead.",
      activation:
        "Reveal this inactive value and enter a nonzero monthly FRA/PIA amount to override the benefit-table entry.",
      effect:
        "Can materially change projected Social Security income, Roth conversion room, Medicare IRMAA exposure, lifetime taxes, portfolio withdrawals, survivor income, and terminal net worth.",
      listAlways: true,
    };
  if (
    s === "Cashflow" &&
    sub === "spending" &&
    l === "core_spending_manual_growth_rate" &&
    coreSpendingGrowthMode() !== "manual_override"
  )
    return {
      active: false,
      reason: "Core spending is set to CPI/general inflation mode.",
      activation:
        "Change Core Spending Increase Method to Manual spending increase override.",
      effect:
        "Would change annual lifestyle spending growth, which can materially affect portfolio withdrawals, lifetime taxes, Monte Carlo success, and terminal net worth.",
    };
  if (
    (s === "Other Assets" &&
      sub === "home" &&
      l.startsWith("home_sale_") &&
      l !== "home_sale_year") ||
    (s === "Model Constants" && sub === "home_sale")
  ) {
    const yr = baseHomeSaleYearRow();
    if (!yr || fieldNumericValue(yr) <= 0)
      return {
        active: false,
        reason: "No home sale year is active for the base plan.",
        activation: "Enter a Base Plan Home Sale Year.",
        effect:
          "Base home sale assumptions change headline Build Impact metrics: home equity timing, sale taxes/costs, reinvested proceeds, future housing, liquidity, lifetime taxes, and terminal net worth.",
        listAlways: l !== "home_sale_price",
      };
  }
  if (
    rowIsStressSellHomeInput(row) &&
    l !== "home_sale_year" &&
    l !== "planned_home_sale_year"
  ) {
    const yr = stressHomeSaleYearRow();
    if (!yr || fieldNumericValue(yr) <= 0)
      return {
        active: false,
        reason: "No Sell Home stress-test year is active.",
        activation:
          "Enter a Sell Home stress-test year. These rows affect the Scenario Analysis sheet, not the headline Build Impact cards.",
        effect:
          "Scenario-only sell-home assumptions change workbook scenario/stress outputs. They do not change base-plan terminal net worth unless you also set the Base Plan Home Sale Year.",
        listAlways: l !== "home_sale_price",
      };
  }
  if (
    s === "Cashflow" &&
    sub === "mortgage" &&
    l === "real_estate_tax_annual_adjustment_pct"
  ) {
    const tax = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Cashflow" &&
        norm(x.subsection) === "mortgage" &&
        norm(x.label) === "annual_real_estate_taxes",
    );
    if (!tax || fieldNumericValue(tax) <= 0)
      return {
        active: false,
        reason:
          "Annual Real Estate Taxes is zero, so the annual adjustment percentage has nothing to adjust.",
        activation: "Enter a nonzero Annual Real Estate Taxes amount.",
        effect:
          "Would increase or decrease future property-tax cash flow, withdrawals, taxes, and terminal net worth.",
      };
  }
  if (s === "Model Constants" && sub === "monte_carlo") {
    const mode = mcEngineModeValue();
    const advancedOnly = new Set([
      "mc_sensitivity_simulations",
      "stochastic_tax_brackets",
      "stochastic_irmaa",
      "healthcare_cost_shocks",
      "healthcare_shock_annual_prob",
      "healthcare_shock_mean_cost",
      "recenter_regime_returns",
      "stochastic_inflation",
      "inflation_sigma",
      "return_inflation_correlation",
      "return_serial_correlation",
    ]);
    if (mode === "quick_vectorized" && advancedOnly.has(l))
      return {
        active: false,
        reason: "Monte Carlo is set to Simple / Quick Vectorized mode.",
        activation:
          "Switch Monte Carlo Engine to Complex / Advanced Exact Scalar.",
        effect:
          "Would affect advisor-ready probability of success, downside ranges, tax/IRMAA stochasticity, Wellness shocks, sensitivity grids, and build time.",
        listAlways: true,
      };
  }
  if (s === "Asset Allocation Policy" && l === "target_pct") {
    const mode = allocationSelectionMode(),
      action = assetActionForSubsection(row.subsection);
    if (allocationModeIsComputed(mode))
      return {
        active: false,
        reason:
          "A computed allocation mode is selected, so saved user target percentages are reference-only.",
        activation: "Choose Use user-specified allocation.",
        effect:
          "Would replace the computed allocation with the user target mix, changing expected return/risk, drift analysis, ETF ideas, Monte Carlo results, and terminal net worth.",
        listAlways: true,
      };
    if (action === "exclude")
      return {
        active: false,
        reason: "This asset class is set to Exclude.",
        activation:
          "Change the selection action to Include or Consider alternate first.",
        effect:
          "Would allow this class into the active allocation target and can change optimizer/user target allocations and risk results.",
      };
  }
  if (
    s === "Asset Class Optimizer Controls" &&
    l === "alternate_asset_class" &&
    assetActionForSubsection(row.subsection) !== "consider_alternate_first"
  )
    return {
      active: false,
      reason: "Selection action is not Consider alternate first.",
      activation:
        "Change Selection to Consider alternate first for this asset class.",
      effect:
        "Would credit an existing asset/source against this class before recommending new liquid exposure.",
    };
  if (
    s === "Asset Class Optimizer Controls" &&
    l === "optimizer_override_pct" &&
    allocationSelectionMode() !== "optimizer_recommendation"
  )
    return {
      active: false,
      reason:
        "User-specified allocation mode is selected; optimizer overrides are ignored.",
      activation: "Choose Use allocation optimizer recommendation.",
      effect:
        "If a full 100% override is entered in optimizer mode, it replaces the computed optimizer target and can change allocation, risk, and projected outcomes.",
    };
  if (s === "Asset Allocation Policy" && l === "holding_period_floor_strength") {
    const globalRow = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Asset Allocation Policy" &&
        norm(x.subsection) === "global" &&
        norm(x.label) === "holding_period_allocation_enabled",
    );
    const globalOn =
      String(globalRow ? valOf(globalRow) : "NO").toUpperCase() === "YES" ||
      String(globalRow ? valOf(globalRow) : "").toUpperCase() === "TRUE";
    if (!globalOn)
      return {
        active: false,
        reason:
          "Holding-Period Allocation Enabled (above) is off, so near-term/long-horizon floors are not applied.",
        activation: "Turn on Holding-Period Allocation Enabled above.",
        effect:
          "Scales how strongly near-term liquid balance is floored toward Cash and durable balance toward growth classes on the optimizer/max-Sharpe recommendation modes.",
        listAlways: true,
      };
  }
  if (
    s === "Asset Allocation Policy" &&
    (l === "real_loss_aware_risk_aversion" || l === "real_loss_aware_weight") &&
    allocationSelectionMode() !== "real_loss_aware"
  )
    return {
      active: false,
      reason:
        "Holding-period real-loss-aware allocation is not the selected allocation mode, so this tuning value is unused.",
      activation:
        "Choose Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation as the allocation mode.",
      effect:
        "Tunes the per-holding-period-bucket solve that mode uses (mean-variance risk aversion, and the weight of the added real-loss-probability penalty).",
      listAlways: true,
    };
  if (s === "Account Policy" && l === "reinvest_dividends") {
    const globalRow = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Economic Assumptions" &&
        norm(x.label) === "reinvest_dividends_default",
    );
    const globalOn =
      String(globalRow ? valOf(globalRow) : "NO").toUpperCase() === "YES" ||
      String(globalRow ? valOf(globalRow) : "").toUpperCase() === "TRUE";
    if (globalOn)
      return {
        active: false,
        reason:
          "Reinvest Dividends Default (global) is turned on, so every investment account reinvests dividends regardless of this per-account setting.",
        activation:
          "Turn off Reinvest Dividends Default above to set per-account overrides.",
        effect:
          "This account would only reinvest dividends independently once the global default is off.",
        listAlways: true,
      };
  }
  if (s === "HSA Policy" && sub === "withdrawals") {
    const modeRow = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "HSA Policy" &&
        norm(x.subsection) === "withdrawals" &&
        norm(x.label) === "hsa_withdrawal_mode",
    );
    const mode = String(modeRow ? valOf(modeRow) : "spend_as_needed")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_");
    if (
      ["hsa_withdrawal_pct", "hsa_annual_spend_pct"].includes(l) &&
      !["annual_pct", "annual_percent"].includes(mode)
    )
      return {
        active: false,
        reason: "HSA withdrawal mode is not annual percentage.",
        activation: "Change HSA withdrawal mode to annual_pct.",
        effect:
          "Would force annual HSA withdrawals and can change taxable income, HSA depletion, portfolio withdrawals, and terminal net worth.",
      };
    if (
      [
        "hsa_withdrawal_start_year",
        "hsa_withdrawal_end_year",
        "withdrawal_window",
      ].includes(l) &&
      !["annual_pct", "annual_percent", "smooth_window", "window"].includes(
        mode,
      )
    )
      return {
        active: false,
        reason: "HSA withdrawal mode is spend as needed.",
        activation:
          "Change HSA withdrawal mode to annual_pct or smooth_window.",
        effect:
          "Would impose a specific HSA drawdown schedule that can affect cash-flow funding and account depletion timing.",
      };
  }
  if (s === "Withdrawal Policy" && sub === "roth_conversion") {
    const policy = rothPolicyValue();
    const none = [
        "none",
        "off",
        "disabled",
        "no_voluntary_conversions",
      ].includes(policy),
      fixed = policy === "fixed_dollar" || policy === "fixed_amount",
      bracket =
        policy === "fill_to_bracket" ||
        policy === "fill_current_bracket" ||
        policy === "fill_target_bracket",
      irmaa = policy === "fill_to_irmaa" || policy === "irmaa_guarded",
      opt =
        policy.includes("optimize") ||
        policy.includes("optimizer") ||
        policy === "balanced_retirement";
    if (none && l !== "roth_conversion_policy")
      return {
        active: false,
        reason: "Roth Conversion Policy is set to no voluntary conversions.",
        activation: "Choose a Roth conversion policy other than none/off.",
        effect:
          "Would enable voluntary conversions that can change lifetime taxes, future RMD pressure, IRMAA exposure, survivor taxes, and terminal/after-tax net worth.",
        listAlways: true,
      };
    if (l === "roth_fixed_annual_amount" && !fixed && !opt)
      return {
        active: false,
        reason:
          "The active Roth policy does not use a fixed annual conversion amount.",
        activation:
          "Choose Fixed-dollar conversion or an optimizer policy that can use a fixed amount.",
        effect:
          "Would add or size annual Roth conversions, changing taxable income, Roth balances, RMDs, IRMAA, and terminal net worth.",
      };
    if (
      [
        "roth_bracket_strategy",
        "roth_target_bracket_rate",
        "roth_headroom_usage_pct",
      ].includes(l) &&
      !bracket &&
      !opt
    )
      return {
        active: false,
        reason: "The active Roth policy does not fill to a tax bracket.",
        activation: "Choose Fill to bracket or an optimizer policy.",
        effect:
          "Would cap or size conversions by bracket headroom, affecting current taxes, future RMDs, IRMAA, and after-tax wealth.",
      };
    if (
      [
        "roth_optimize_terminal_weight",
        "roth_optimize_lifetime_tax_weight",
        "roth_tax_discount_rate",
        "roth_objective_mode",
        "estate_tax_objective_mode",
        "legacy_objective_mode",
        "future_tax_rate_stress_pct",
        "future_tax_risk_weight",
        "inheritance_tax_burden_weight",
        "heir_ordinary_tax_rate_assumption_pct",
        "pre_tax_bequest_penalty_pct",
        "roth_bequest_preference_bonus_pct",
        "survivor_tax_risk_weight",
      ].includes(l) &&
      !opt &&
      !bracket
    )
      return {
        active: false,
        reason:
          "The active Roth policy is not using optimizer or bracket calibration.",
        activation: "Choose an optimizer-style Roth policy.",
        effect:
          "Would change Roth strategy scoring, lifetime tax tradeoffs, survivor protection, estate/legacy weighting, and recommended conversions.",
      };
  }
  return { active: true };
}
Object.assign(window, {
  fieldNumericValue, moduleOffImpactWarning, rawRowsForStep, rowBuildUsageState, rowModuleGate,
});
