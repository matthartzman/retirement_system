"""Module catalog — the single source of truth for the Inputs/Outputs reframing.

This is the codified form of ``documentation/archive/MODULE_REFRAMING_INPUTS_OUTPUTS.md``
(v2). It classifies every workbook output module by the *question it answers*
and records, for each, the inputs and prerequisite outputs it needs plus a
demand band. Later phases (UI page gating, prerequisite auto-selection, section
ordering) consume this instead of the scattered hand-written guards.

Design constraints:

* **Zero heavy dependencies.** This module imports nothing beyond the stdlib so
  it can be loaded and validated without pulling in the reporting/engine stack
  (numpy, openpyxl, …). ``OPTIONAL_MODULE_SHEETS`` and the ``module_enabled``/
  ``module_status`` gating functions (A9) live here rather than in
  ``src.reporting.workbook_common`` for the same reason: ``config_service``
  needs per-module gating status for the UI without importing that
  openpyxl-backed package. ``workbook_common`` imports these back from here.
* **Additive.** Nothing here changes existing behavior yet. It provides the data
  and the resolver API that the follow-up phases wire in.

Two top-level categories:

* **Inputs** (:data:`INPUT_MODULES`) — the plan's facts, assumptions, and the
  levers the household controls. Consumed, never recommended.
* **Outputs** (:data:`CATALOG`) — the optional/selectable modules. Each produces
  exactly one *kind* of result.

The five output kinds, defined by the question each answers, with the axis that
separates the two that used to blur together:

    Optimization changes a variable the household *controls* (a lever).
    Stress test changes a variable *outside* their control (a risk).
"""
from __future__ import annotations

import os
from collections import namedtuple
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Output kinds and demand bands
# ─────────────────────────────────────────────────────────────────────────────
PROJECTION = "projection"
OPTIMIZATION = "optimization"
COMPARISON = "comparison"
PROTECTION = "protection"
STRESS_TEST = "stress_test"
WORKSHEET = "worksheet"
DIAGNOSTICS = "diagnostics"
REFERENCE = "reference"

KINDS = (PROJECTION, OPTIMIZATION, COMPARISON, PROTECTION, STRESS_TEST,
         WORKSHEET, DIAGNOSTICS, REFERENCE)

KIND_QUESTION = {
    PROJECTION:      "What happens to the plan as-is over time?",
    OPTIMIZATION:    "What controllable lever should I change, and by how much?",
    COMPARISON:      "Of the alternatives I named, which scores better?",
    PROTECTION:      "How much coverage should I hold against this risk?",
    STRESS_TEST:     "Does the plan survive events outside my control?",
    WORKSHEET:       "What do the figures computed elsewhere add up to?",
    DIAGNOSTICS:     "Is the model itself trustworthy?",
    REFERENCE:       "What inputs and methods produced this?",
}

# ── Domains (#330 §4.2) ──────────────────────────────────────────────────────
# The second, independent axis: `kind` is the shape of the answer a module
# produces, `domain` is the part of life it concerns. The workbook groups by
# kind (a flat Excel tab strip); the Plan Features switch nav groups by domain
# (the user is asking "is this about me"). NEITHER IS DERIVABLE FROM THE OTHER:
# Housing Comparison is an OPTIMIZATION in the Housing & Property domain,
# Monte Carlo a STRESS_TEST in Risk & Resilience, Lifetime Taxes a PROJECTION
# in Taxes. validate() asserts every module declares both, separately.
INCOME_BENEFITS = "Income & Benefits"
SPENDING = "Spending"
HOUSING_PROPERTY = "Housing & Property"
INVESTMENTS = "Investments"
TAXES = "Taxes"
ASSETS_PROTECTION = "Assets & Protection"
ESTATE_LEGACY = "Estate & Legacy"
FAMILY_BUSINESS = "Family & Business"
RISK_RESILIENCE = "Risk & Resilience"
REPORTS_DOCUMENTATION = "Reports & Documentation"

DOMAINS = (INCOME_BENEFITS, SPENDING, HOUSING_PROPERTY, INVESTMENTS, TAXES,
           ASSETS_PROTECTION, ESTATE_LEGACY, FAMILY_BUSINESS, RISK_RESILIENCE,
           REPORTS_DOCUMENTATION)

# High demand → obscure, five bands (ordered most- to least-common).
HIGH = "high"
MEDIUM_HIGH = "medium_high"
MEDIUM = "medium"
LOW = "low"
NICHE = "niche"

DEMAND_BANDS = (HIGH, MEDIUM_HIGH, MEDIUM, LOW, NICHE)
DEMAND_RANK = {band: i for i, band in enumerate(DEMAND_BANDS)}

# ``What-If``'s side-by-side layout is a *presentation mode*; the fact that it
# scores alternatives the user supplied is its `kind` (COMPARISON, #329 §3.1,
# promoted from this flag). Same string on purpose — the flag was a half-built
# version of the kind — but they answer different questions: `mode` is how the
# sheet is laid out, `kind` is what the sheet is. validate() asserts the flag
# only ever appears on a COMPARISON module.
MODE_COMPARISON = "comparison"

# ─────────────────────────────────────────────────────────────────────────────
# Input modules (the control/fact surface every Output draws from)
# ─────────────────────────────────────────────────────────────────────────────
INPUT_MODULES: Dict[str, Dict[str, object]] = {
    "household":       {"label": "Household & timing",     "files": ["client_household.csv"]},
    "income":          {"label": "Income",                 "files": ["client_income.csv"]},
    "spending":        {"label": "Spending",               "files": ["client_spending.csv", "client_spending_budget_lines.csv"]},
    "assets":          {"label": "Assets & liquidity",     "files": ["client_assets.csv"]},
    "liabilities":     {"label": "Liabilities",            "files": ["client_liabilities.csv"]},
    "holdings":        {"label": "Holdings & lots",        "files": ["client_holdings.csv", "security_master.csv"]},
    "planning_levers": {"label": "Planning Levers",        "files": ["client_policy.csv", "target_allocation.csv", "asset_class_optimizer_controls.csv"]},
    "insurance_estate":{"label": "Insurance & estate",     "files": ["client_insurance_estate.csv"]},
    "business":        {"label": "Business",               "files": ["client_business.csv"]},
    "assumptions":     {"label": "Assumptions (economic/tax)", "files": ["reference_data/*", "tax_law_v10.json"]},
    "pricing":         {"label": "Market pricing",         "files": ["security_master.csv"]},
    "ytd":             {"label": "YTD actuals",            "files": ["ytd_transactions.csv", "ytd_account_setup.csv"]},
    "toggles":         {"label": "Module toggles",         "files": ["client_optional_functions.csv"]},
}

ALL_INPUTS: Tuple[str, ...] = tuple(INPUT_MODULES)


# ─────────────────────────────────────────────────────────────────────────────
# Output module spec
# ─────────────────────────────────────────────────────────────────────────────
RequiredInput = Tuple[str, Tuple[str, ...]]  # (input_module_id, (specific elements, ...))


@dataclass(frozen=True)
class OutputModule:
    key: str
    name: str
    kind: str
    demand: str
    description: str
    # `domain` is required (validate() asserts it) but declared with a default
    # so it can be passed by keyword, like every other optional field, rather
    # than forcing 40 call sites to pass it positionally between `demand` and
    # `description`. A module that omits it fails at import, not silently.
    domain: Optional[str] = None
    # ``optional`` mirrors membership in workbook_common.OPTIONAL_MODULE_SHEETS:
    # optional modules carry a client_optional_functions.csv toggle; core
    # modules are always on. ``sheet`` is the legacy build-time sheet name (the
    # stable internal identity used by the gate); ``tab`` is the final
    # presentation label. ``requires_outputs`` are prerequisite output keys.
    #
    # ``tab`` is DOCUMENTATION, not the source of truth: the real label is
    # derived per build from SHEET_LETTER_ORDER, so a letter here is only ever
    # a copy. Eight of them had silently drifted a letter out of date (adding
    # HSA Drawdown at 2B shifted the whole group and nothing noticed), which is
    # the hand-typed-twin problem #329 §3.1 exists to end. They are corrected
    # here; W3 removes the field once cross-references resolve through a slug.
    optional: bool = False
    sheet: Optional[str] = None
    tab: Optional[str] = None
    mode: Optional[str] = None
    requires_inputs: Tuple[RequiredInput, ...] = field(default_factory=tuple)
    requires_outputs: Tuple[str, ...] = field(default_factory=tuple)
    # §7.4 (system review Wave 3.5b): the single source of truth for the two
    # ad-hoc gates dashboard.js used to hand-maintain separately —
    # ``dashboard_step`` names the nav step this module owns outright (the
    # step is hidden while the module is off); ``csv_sections`` names the
    # input-CSV ``section`` value(s) this module gates within a step that
    # stays visible regardless (e.g. DAF rows inside "Other Spending").
    # Populated only for modules that actually gate dashboard input
    # visibility today — most Optimization/Stress/Diagnostics modules gate a
    # workbook *sheet*, not an input page, and have neither.
    dashboard_step: Optional[str] = None
    csv_sections: Tuple[str, ...] = field(default_factory=tuple)


def _in(module: str, *elements: str) -> RequiredInput:
    return (module, tuple(elements))


# The deterministic base projection every optimization/stress output re-runs or
# reads. Referenced as a prerequisite by name so the resolver can pull it in.
BASE_PROJECTION: Tuple[str, ...] = ("net_worth", "cash_flow")


_OUTPUTS: List[OutputModule] = [
    # ── Projection ──────────────────────────────────────────────────────────
    OutputModule(
        "net_worth", "Net Worth", PROJECTION, HIGH,
        "Year-by-year total net worth; the plan's headline trajectory.",
        domain=REPORTS_DOCUMENTATION,
        sheet="5. Net Worth Projection", tab="1B. Net Worth",
        requires_inputs=(_in("household", "ages", "timing"), _in("assets", "balances"),
                         _in("liabilities", "balances"), _in("holdings", "balances"),
                         _in("assumptions", "growth", "cma")),
    ),
    OutputModule(
        "cash_flow", "Cash Flow", PROJECTION, HIGH,
        "Annual inflows/outflows, funding gaps, and withdrawal need.",
        domain=REPORTS_DOCUMENTATION,
        sheet="6. Cash Flow Projection", tab="1C. Cash Flow",
        requires_inputs=(_in("income", "all_streams"), _in("spending", "all"),
                         _in("liabilities", "payments"), _in("household", "ss", "timing")),
    ),
    OutputModule(
        "balance_sheet", "Balance Sheet", PROJECTION, HIGH,
        "Point-in-time assets/liabilities by account and tax type.",
        domain=REPORTS_DOCUMENTATION,
        sheet="3. Balance Sheet", tab="1D. Balance Sheet",
        requires_inputs=(_in("assets"), _in("liabilities"), _in("holdings")),
    ),
    OutputModule(
        "executive_summary", "Executive Summary", PROJECTION, HIGH,
        "One-page KPI roll-up of the whole plan.",
        domain=REPORTS_DOCUMENTATION,
        sheet="1. Executive Summary", tab="1A. Executive Summary",
        requires_outputs=("net_worth", "cash_flow", "balance_sheet"),
    ),
    OutputModule(
        "lifetime_tax_projection", "Lifetime Taxes", PROJECTION, HIGH,
        "Cumulative federal/state/NIIT/IRMAA/payroll/cap-gains over the plan.",
        domain=TAXES,
        optional=True, sheet="7. Lifetime Tax", tab="1F. Lifetime Taxes",
        requires_inputs=(_in("income"), _in("spending"), _in("holdings"),
                         _in("assumptions", "tax_law")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        # #221: merged into spending_summary below -- Spending Summary already
        # contained every Core Expenses number this sheet showed (same
        # underlying spending_summary_taxonomy() call), so the "Model core
        # spending assumption" comparison (the one thing unique to this sheet)
        # moved there instead of duplicating a whole sheet.
        "spending_summary", "Spending Summary", PROJECTION, MEDIUM_HIGH,
        "Category roll-up of spend, including a Core Expenses vs. modeled-assumption reconciliation.",
        domain=SPENDING,
        sheet="29. Spending Summary", tab="1G. Spending Summary",
        requires_inputs=(_in("spending"),),
    ),
    OutputModule(
        "charts_dashboard", "Charts", PROJECTION, MEDIUM_HIGH,
        "Visual consolidation of the projection series.",
        domain=INVESTMENTS,
        optional=True, sheet="8. Charts Dashboard", tab="1E. Charts",
        requires_outputs=("net_worth", "cash_flow", "asset_allocation"),
    ),

    # ── Optimization: decision levers ─────────────────────────────────────────
    OutputModule(
        "roth_conversion_plan", "Roth Conversion", OPTIMIZATION, HIGH,
        "Conversion amounts / bracket-fill; quantifies lifetime tax savings.",
        domain=TAXES,
        optional=True, sheet="11. Roth Conversion", tab="2A. Roth Conversion",
        requires_inputs=(_in("planning_levers", "roth_policy", "forced_conversions"),
                         _in("income"), _in("assumptions", "brackets", "irmaa")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="roth_conversion",
    ),
    OutputModule(
        # Registry gap closed (#329 §2.1): a textbook plan optimizer — it
        # enumerates drawdown orders, scores them and ranks — that had a sheet
        # and a builder but no catalog record, so nothing could reason about
        # it. Core for now: making it toggleable is W8b, not W1.
        "hsa_drawdown", "HSA Drawdown", OPTIMIZATION, MEDIUM,
        "Drawdown order for HSA dollars; self-gates on hsa_withdrawal_mode == 'optimize'.",
        domain=TAXES,
        sheet="11C. HSA Drawdown", tab="2B. HSA Drawdown",
        requires_inputs=(_in("planning_levers", "hsa_withdrawal_mode"),
                         _in("assets"), _in("assumptions", "brackets")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        # Registry gap closed (#329 §2.1). Filed under Optimizers, but by its
        # own docstring it "derives nothing new" — every column reads a value
        # the engine or another sheet already computed. That is a WORKSHEET,
        # and W0/V3 confirmed its home is Reports rather than a one-tab
        # Reference section.
        "tax_capacity", "Tax Capacity", WORKSHEET, MEDIUM,
        "Consolidated per-year bracket, IRMAA and ACA headroom, assembled from four other sheets.",
        domain=TAXES,
        sheet="11B. Tax Capacity", tab="1I. Tax Capacity",
        requires_inputs=(_in("income"), _in("assumptions", "brackets", "irmaa")),
        requires_outputs=BASE_PROJECTION + ("lifetime_tax_projection",),
    ),
    OutputModule(
        "asset_allocation", "Asset Allocation", OPTIMIZATION, HIGH,
        "Target vs actual mix, drift, and rebalancing guidance.",
        domain=INVESTMENTS,
        sheet="4. Asset Allocation", tab="2C. Asset Allocation",
        requires_inputs=(_in("planning_levers", "targets", "controls"), _in("holdings"),
                         _in("assumptions", "cma")),
    ),
    OutputModule(
        "social_security_timing", "Social Security", OPTIMIZATION, HIGH,
        "Optimal claiming age; lifetime-benefit comparison.",
        domain=INCOME_BENEFITS,
        optional=True, sheet="10. Social Security", tab="2E. Social Security",
        requires_inputs=(_in("household", "ss_policy", "dob", "earnings"),
                         _in("planning_levers", "claiming_age")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "retirement_strategy", "Withdrawal Sequencing", OPTIMIZATION, MEDIUM_HIGH,
        "Draw order across account tax types.",
        domain=INVESTMENTS,
        optional=True, sheet="9. Retirement Strategy", tab="9. Retirement Strategy",
        requires_inputs=(_in("planning_levers", "sequencing"), _in("assets"), _in("holdings")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "asset_location", "Asset Location", OPTIMIZATION, MEDIUM_HIGH,
        "Which assets to hold in which tax bucket.",
        domain=INVESTMENTS,
        sheet="24. Asset Location", tab="24. Asset Location",
        requires_inputs=(_in("holdings", "lots"), _in("planning_levers", "location_policy"),
                         _in("assumptions", "tax_rates")),
    ),
    OutputModule(
        "what_if_analysis", "What-If / Scenario", COMPARISON, MEDIUM_HIGH,
        "Side-by-side of 2-3 saved lever bundles with deltas (comparison mode).",
        domain=RISK_RESILIENCE,
        optional=True, sheet="16. Scenario Analysis", tab="16. Scenario Analysis",
        mode=MODE_COMPARISON,
        requires_inputs=(_in("planning_levers", "bundled_positions"),),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="scenarios",
    ),
    OutputModule(
        "tax_loss_harvesting", "Tax-Loss Harvesting", OPTIMIZATION, MEDIUM,
        "Harvestable losses given current lots.",
        domain=TAXES,
        optional=True, sheet="12B. Tax-Loss Harvesting", tab="2I. Tax-Loss Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "gain_harvesting", "Gain Harvesting", OPTIMIZATION, MEDIUM,
        "0%-bracket long-term gains harvestable given current lots.",
        domain=TAXES,
        optional=True, sheet="12C. Gain Harvesting", tab="2N. Gain Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "charitable_giving", "Charitable Giving", OPTIMIZATION, MEDIUM,
        "Bunching / QCD / DAF strategy and tax effect.",
        domain=TAXES,
        optional=True, sheet="12. Charitable Giving", tab="2G. Charitable Giving",
        # QCD (item 4.1) and DAF-appreciated-securities (item 4.2) fields
        # landed in Wave 4, after this entry was first authored — added here
        # as the Wave 3.5a rework the review's own §9.1 called for ("new
        # modules should be authored against the reframed registry, not
        # retrofitted into it").
        requires_inputs=(_in("assets", "daf", "daf_appreciated_securities"),
                         _in("spending", "qcd"), _in("income"),
                         _in("household", "age"), _in("assumptions", "brackets")),
        dashboard_step="entity_charitable", csv_sections=("DAF",),
    ),
    OutputModule(
        "state_residency", "State Residency", COMPARISON, MEDIUM,
        "Tax impact of relocating.",
        domain=HOUSING_PROPERTY,
        optional=True, sheet="13. State Residency", tab="2D. State Residency",
        requires_inputs=(_in("planning_levers", "residency_choice"), _in("income"),
                         _in("assumptions", "state_tax")),
    ),
    OutputModule(
        # Slice 4 (2026-09-09 housing-estimate design, §4, §7.0 H9-H11):
        # a three-axis coordinate-descent sweep of the household's whole
        # future housing trajectory -- current-home sale year, Step 1 and
        # Step 2 type x year -- run from two axis orderings with the better
        # kept, then refined with real Monte Carlo. Upgrades Slice 3's
        # 2-candidate v0 in place, same sheet, same toggle.
        "housing_trajectory_comparison", "Housing Comparison", OPTIMIZATION, LOW,
        "Sweeps the current-home sale year and both future housing steps (buy vs. rent x year) "
        "by coordinate descent, ranked on the same LCV basis as the Social Security sweep.",
        domain=HOUSING_PROPERTY,
        optional=True, sheet="38. Housing Comparison", tab="2O. Housing Comparison",
        requires_inputs=(_in("household", "next_housing_steps"), _in("assumptions", "growth")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "estate_legacy_plan", "Estate & Legacy", OPTIMIZATION, MEDIUM,
        "Estate-tax exposure, legacy/bequest structure, beneficiary/titling audit, "
        "gifting schedule, and per-beneficiary 10-year drawdown sensitivity.",
        domain=ESTATE_LEGACY,
        optional=True, sheet="14. Estate Plan", tab="2H. Estate & Legacy Planning",
        # Account titling (4.7), gifting schedule (4.8), and the per-beneficiary
        # drawdown (4.9) all shipped in Wave 4, after this entry was first
        # authored, and landed as new sections on this same sheet rather than
        # new catalog entries of their own (edit-only CSV sections, no
        # dedicated dashboard step yet) - added here as the Wave 3.5a rework
        # the review's own §9.1 called for.
        requires_inputs=(_in("insurance_estate", "estate_inputs", "account_titling", "gifting_schedule"),
                         _in("assets"), _in("household", "ages"),
                         _in("assumptions", "estate_constants")),
    ),
    OutputModule(
        "education_funding_529", "Education Funding 529", OPTIMIZATION, LOW,
        "529 sizing vs education goals.",
        domain=FAMILY_BUSINESS,
        optional=True, sheet="30. Education Funding", tab="2J. Education Funding",
        requires_inputs=(_in("insurance_estate", "529_accounts", "goals"),
                         _in("assumptions", "growth")),
        csv_sections=("Education Funding",),
    ),
    OutputModule(
        "equity_compensation", "Equity Compensation", OPTIMIZATION, LOW,
        "RSU / ISO / NSO / ESPP tax and timing.",
        domain=FAMILY_BUSINESS,
        optional=True, sheet="35. Equity Compensation", tab="2K. Equity Compensation",
        requires_inputs=(_in("insurance_estate", "grants"), _in("assumptions", "tax")),
        csv_sections=("Equity Compensation",),
    ),
    OutputModule(
        "scorp_vs_llc", "S-Corp vs LLC", COMPARISON, LOW,
        "Entity-structure tax comparison for the self-employed.",
        domain=FAMILY_BUSINESS,
        sheet="S-Corp vs LLC", tab="2F. S-Corp vs LLC",
        requires_inputs=(_in("income", "self_employment"), _in("business"),
                         _in("assumptions", "tax")),
    ),
    OutputModule(
        "business_succession", "Business Succession", OPTIMIZATION, LOW,
        "Buy-sell / key-person / valuation planning.",
        domain=FAMILY_BUSINESS,
        optional=True, sheet="34. Business Succession", tab="2M. Business Succession",
        requires_inputs=(_in("business", "entity", "valuation", "funding"),),
    ),
    OutputModule(
        "special_needs_planning", "Special-Needs Planning", OPTIMIZATION, NICHE,
        "SNT / ABLE structure for a dependent.",
        domain=FAMILY_BUSINESS,
        optional=True, sheet="36. Special-Needs Planning", tab="2L. Special-Needs Planning",
        requires_inputs=(_in("household", "dependents"), _in("insurance_estate")),
    ),

    # ── Optimization: protection decisions (each requires a Stress result) ────
    OutputModule(
        "life_insurance_need", "Life Insurance Need", PROTECTION, MEDIUM,
        "Coverage to buy vs survivor shortfall — a decision that reads a stress.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="19. Life Insurance", tab="3C. LTC + Life Insurance",
        requires_inputs=(_in("insurance_estate", "policies"), _in("income")),
        requires_outputs=("survivor_stress_test",),
    ),
    OutputModule(
        "existing_life_insurance", "Existing Life Insurance", PROTECTION, LOW,
        "Adequacy of in-force policies.",
        domain=ASSETS_PROTECTION,
        optional=True, sheet="31. Existing Life Insurance", tab="3D. Existing Life Insurance",
        requires_inputs=(_in("insurance_estate", "life_policies"),),
        requires_outputs=("survivor_stress_test",),
        # Pre-existing dashboard.js behavior (ROW_MODULE_GATES), preserved as-is:
        # ALL "Insurance In Force" rows are gated by this module's toggle alone,
        # even a row whose own policy_type is Disability/LTC/Umbrella. Not
        # fixed here — out of scope for this refactor, which preserves
        # existing behavior exactly.
        csv_sections=("Insurance In Force",),
    ),
    OutputModule(
        "disability_income_insurance", "Disability Income", PROTECTION, LOW,
        "DI coverage vs income-replacement need.",
        domain=ASSETS_PROTECTION,
        optional=True, sheet="32. Disability Income", tab="3E. Disability Income",
        requires_inputs=(_in("insurance_estate", "di_policies"), _in("income")),
        requires_outputs=("cash_flow",),
    ),
    OutputModule(
        "property_casualty_umbrella", "P&C / Umbrella", PROTECTION, NICHE,
        "Liability coverage adequacy vs net worth.",
        domain=ASSETS_PROTECTION,
        optional=True, sheet="33. P&C Umbrella", tab="3F. P&C Umbrella",
        requires_inputs=(_in("insurance_estate", "pc_policies"),),
        requires_outputs=("net_worth",),
    ),

    # ── Stress test (exogenous events) ────────────────────────────────────────
    OutputModule(
        "market_luck_stress_test", "Monte Carlo", STRESS_TEST, HIGH,
        "Probability of success across market-return paths.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="15. Market-Luck Stress Test", tab="3A. Monte Carlo",
        requires_inputs=(_in("assumptions", "cma", "correlations"),
                         _in("planning_levers", "mc_settings")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="monte_carlo_options",
    ),
    OutputModule(
        "survivor_stress_test", "Survivor / Early Death", STRESS_TEST, MEDIUM,
        "Plan solvency after one spouse's early death.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="18. Survivor Stress Test", tab="3B. Survivor",
        requires_inputs=(_in("household", "survivor_state"),
                         _in("income", "survivor_continuation"), _in("insurance_estate")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="survivor_stress",
    ),
    OutputModule(
        "long_term_care_stress", "LTC Stress", STRESS_TEST, MEDIUM,
        "Impact of a long-term-care event.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="17. LTC Stress Test", tab="3C. LTC + Life Insurance",
        requires_inputs=(_in("insurance_estate", "ltc_policy"), _in("assets", "liquidity"),
                         _in("assumptions", "ltc_cost")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="ltc_stress",
    ),
    OutputModule(
        "divorce_qdro", "Divorce / QDRO", STRESS_TEST, NICHE,
        "Plan under an imposed asset split (exogenous life event).",
        domain=RISK_RESILIENCE,
        optional=True, sheet=None, tab=None,
        requires_inputs=(_in("household", "divorce_assumptions"), _in("assets"), _in("holdings")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="divorce_options",
    ),

    # ── Diagnostics ──────────────────────────────────────────────────────────
    OutputModule(
        "quality_control", "Quality Control", DIAGNOSTICS, MEDIUM,
        "Pass/fail checks on the projection's internal consistency.",
        domain=REPORTS_DOCUMENTATION,
        sheet="21. Quality Control", tab="4D. Quality Control",
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "rmd_audit", "RMD Audit", DIAGNOSTICS, MEDIUM,
        "Verifies RMD amounts/timing against tax rules.",
        domain=TAXES,
        optional=True, sheet="20. RMD Audit", tab="4E. RMD Audit",
        requires_inputs=(_in("household", "ages"), _in("assumptions", "rmd_tables")),
        requires_outputs=("net_worth",),
    ),
    OutputModule(
        "account_reconciliation", "Account Reconciliation", DIAGNOSTICS, MEDIUM,
        "Reconciles modeled balances against YTD actuals.",
        domain=REPORTS_DOCUMENTATION,
        sheet="25. Account Reconciliation", tab="4C. Account Reconciliation",
        requires_inputs=(_in("holdings"), _in("ytd", "transactions", "setup")),
    ),

    # ── Reference / Documentation ─────────────────────────────────────────────
    OutputModule(
        "planning_levers_echo", "Planning Levers (echo)", REFERENCE, MEDIUM,
        "Restates the chosen dial positions with their source.",
        domain=REPORTS_DOCUMENTATION,
        sheet="27. Planning Levers", tab="4H. Planning Levers",
        requires_inputs=(_in("planning_levers"),),
    ),
    OutputModule(
        "assumptions_ref", "Assumptions", REFERENCE, MEDIUM,
        "Echoes the economic/tax assumptions used, for auditability.",
        domain=REPORTS_DOCUMENTATION,
        sheet="2. Assumptions", tab="4B. Assumptions",
        requires_inputs=(_in("assumptions"),),
    ),
    OutputModule(
        "plan_data_ref", "Plan Data", REFERENCE, MEDIUM,
        "Snapshot of all inputs behind the run.",
        domain=REPORTS_DOCUMENTATION,
        sheet="Plan Data", tab="4A. Plan Data",
        requires_inputs=tuple(_in(m) for m in ALL_INPUTS),
    ),
    OutputModule(
        "methodology_rerun", "Methodology & Re-Run", REFERENCE, LOW,
        "Explains the model and how to reproduce the run.",
        domain=REPORTS_DOCUMENTATION,
        optional=True, sheet="23. Methodology", tab="4F. Methodology",
    ),
    OutputModule(
        # Registry gap closed (#330 §7.1). Restates recommendations modeled on
        # other sheets, so it is a WORKSHEET rather than a COMPARISON: the
        # alternatives are not two things the user named, they are this plan
        # before and after the recommendations it already tracks.
        "current_vs_proposed", "Current vs Proposed", WORKSHEET, MEDIUM,
        "Every tracked recommendation, active or proposed, with its cash-flow delta.",
        domain=REPORTS_DOCUMENTATION,
        sheet="37. Current vs Proposed", tab="1H. Current vs. Proposed",
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "glossary", "Glossary", REFERENCE, LOW,
        "Defines terms used across the workbook.",
        domain=REPORTS_DOCUMENTATION,
        optional=True, sheet="22. Glossary", tab="4G. Glossary",
    ),
]

CATALOG: Dict[str, OutputModule] = {m.key: m for m in _OUTPUTS}


# ─────────────────────────────────────────────────────────────────────────────
# Query / resolver API
# ─────────────────────────────────────────────────────────────────────────────
def get(key: str) -> OutputModule:
    """Return the spec for ``key`` (raises KeyError if unknown)."""
    return CATALOG[key]


def by_kind(kind: str) -> List[OutputModule]:
    """Outputs of ``kind``, ordered by descending demand then name."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    return sorted((m for m in _OUTPUTS if m.kind == kind),
                  key=lambda m: (DEMAND_RANK[m.demand], m.name))


def step_gate_map() -> Dict[str, str]:
    """{dashboard_step_id: optional_module_key} for every module that owns a
    nav step outright (§7.4). The frontend hides that step whenever the
    module is off, replacing a hand-maintained if/else chain
    (``stepGatedByOptionalModule``) with this single source of truth.
    """
    return {m.dashboard_step: m.key for m in _OUTPUTS if m.dashboard_step}


def section_gate_map() -> Dict[str, str]:
    """{csv_section: optional_module_key} for every input-CSV section a
    module gates within a step that stays visible regardless (§7.4).
    Replaces the hand-maintained ``ROW_MODULE_GATES`` object in dashboard.js.
    """
    out: Dict[str, str] = {}
    for m in _OUTPUTS:
        for section in m.csv_sections:
            out[section] = m.key
    return out


def optional_keys() -> List[str]:
    """Keys of modules that carry a client_optional_functions.csv toggle."""
    return [m.key for m in _OUTPUTS if m.optional]


def core_keys() -> List[str]:
    """Keys of always-on core modules (no toggle)."""
    return [m.key for m in _OUTPUTS if not m.optional]


def prerequisite_outputs(key: str, transitive: bool = True) -> List[str]:
    """Prerequisite output keys for ``key`` (transitive by default, excludes self).

    Order is deterministic: direct prerequisites first, then their prerequisites,
    depth-first, de-duplicated.
    """
    if key not in CATALOG:
        raise KeyError(key)
    ordered: List[str] = []
    stack = list(CATALOG[key].requires_outputs)
    while stack:
        dep = stack.pop(0)
        if dep in ordered or dep == key:
            continue
        ordered.append(dep)
        if transitive:
            stack.extend(CATALOG[dep].requires_outputs)
    return ordered


# ─────────────────────────────────────────────────────────────────────────────
# Sheet registry (system review 2026-08-04, architect finding
# `sheet-identity-scattered-across-five-tables`)
# ─────────────────────────────────────────────────────────────────────────────
# Sheet identity used to be hand-typed across five places: this module's
# OPTIONAL_MODULE_SHEETS, plus workbook_common.py's V5_LAYOUT,
# WORKBOOK_SECTION_LAYOUT, SHEET_LETTER_ORDER, and SHEET_DISPLAY_TITLES. Adding
# a sheet meant editing all five and hoping none drifted. SHEET_REGISTRY is now
# the one place a sheet's identity is declared; every one of those five tables
# is derived from it (OPTIONAL_MODULE_SHEETS immediately below; the other four
# in workbook_common.py). tests/test_sheet_table_consistency.py is the safety
# net that pins the derived shape against the pre-registry hand-typed one.
#
# Lives here (not workbook_common.py) for the same reason OPTIONAL_MODULE_SHEETS
# always has: config_service and other API callers need per-module gating
# status (module_status, below) without importing the openpyxl-backed
# reporting package — workbook_common imports these back from here.
#
# Fields:
#   v5_code       -- section code used by the legacy build-time V5_LAYOUT list,
#                    or None for sheets created by a dedicated code path
#                    instead of the main creation loop ('Plan Data', 'S-Corp
#                    vs LLC').
#   section       -- physical tab-group code in WORKBOOK_SECTION_LAYOUT, or
#                    None for sheets absent from the visible nav (hidden
#                    helpers, plus a few reports intentionally excluded).
#   section_rank  -- display order within `section`, independent of
#                    letter_rank. The two ranks order a sheet within its group
#                    and may differ; the two *groups* may not. `section` and
#                    `letter_prefix` naming different groups is the `2I` /
#                    `3D`-`3F` contradiction (#329 §3.1) -- '27. Planning
#                    Levers' used to sit in section '4' while lettered into
#                    '2' -- and validate() now rejects it at import.
#   letter_prefix -- number-prefix group in SHEET_LETTER_ORDER, or None.
#   letter_rank   -- display order within `letter_prefix`.
#   display       -- title after "1A. " in the final sheet name, or None if
#                    the sheet never appears in the final numbered/lettered
#                    nav.
#   module_key    -- OPTIONAL_MODULE_SHEETS gating key, or None if always-on.
SheetSpec = namedtuple(
    'SheetSpec',
    'v5_code section section_rank letter_prefix letter_rank display module_key',
)


def _spec(v5_code=None, section=None, section_rank=None, letter_prefix=None,
          letter_rank=None, display=None, module_key=None):
    return SheetSpec(v5_code, section, section_rank, letter_prefix, letter_rank,
                      display, module_key)


# The kind -> letter-group map the invariant below enforces. #329 §3.1: a
# sheet's workbook group is a CONSEQUENCE of its module's kind, not a second
# fact typed beside it. Phase 1 (this) asserts the two agree; W3 deletes the
# hand-typed `section`/`letter_prefix` fields and derives them from here.
#
# This is the map as the workbook stands TODAY, before W3's regrouping. W3
# changes it -- COMPARISON moves to its own '3' and PROTECTION joins the
# renamed '4. Risks' -- and that edit is the regrouping, which is why the map
# is a named table rather than an expression inlined in validate().
#
# WORKSHEET shares '1' with PROJECTION deliberately: a worksheet restates
# figures computed elsewhere, which is what a report does, and W0/V3 rejected
# a one-tab Reference section for the single sheet this affects. REFERENCE is
# separate because those four sheets document how the run was produced rather
# than what it says.
KIND_LETTER_PREFIX: Dict[str, str] = {
    PROJECTION:   '1',
    WORKSHEET:    '1',
    OPTIMIZATION: '2',
    COMPARISON:   '2',
    PROTECTION:   '3',
    STRESS_TEST:  '3',
    DIAGNOSTICS:  '4',
    REFERENCE:    '4',
}

SHEET_REGISTRY = {
    '1. Executive Summary':        _spec('1', '1', 0, '1', 0, 'Executive Summary'),
    'Plan Data':                   _spec(None, '4', 0, '4', 0, 'Plan Data'),
    '2. Assumptions':              _spec('4', '4', 1, '4', 1, 'Assumptions'),
    '3. Balance Sheet':            _spec('1', '1', 3, '1', 3, 'Balance Sheet'),
    '4. Asset Allocation':         _spec('2', '2', 1, '2', 1, 'Asset Allocation'),
    '5. Net Worth Projection':     _spec('1', '1', 1, '1', 1, 'Net Worth'),
    '6. Cash Flow Projection':     _spec('1', '1', 2, '1', 2, 'Cash Flow'),
    '7. Lifetime Tax':             _spec('1', '1', 5, '1', 5, 'Lifetime Taxes', 'lifetime_tax_projection'),
    '8. Charts Dashboard':         _spec('1', '1', 4, '1', 4, 'Charts', 'charts_dashboard'),
    '9. Retirement Strategy':      _spec('1', module_key='retirement_strategy'),
    'S-Corp vs LLC':               _spec(None, '2', 4, '2', 4, 'S-Corp vs LLC'),
    '10. Social Security':         _spec('2', '2', 3, '2', 3, 'Social Security', 'social_security_timing'),
    '11. Roth Conversion':         _spec('2', '2', 0, '2', 0, 'Roth Conversion', 'roth_conversion_plan'),
    # section_rank/letter_rank are sort keys, not slots -- 0.5 sits it right
    # after Roth Conversion (rank 0) without renumbering anything else. Its
    # content is optimizer-mode-gated (hsa_withdrawal_mode == 'optimize'),
    # not a client_optional_functions.csv toggle, so module_key stays None
    # like 11B: always created, self-gates its own content.
    '11C. HSA Drawdown':           _spec('2', '2', 0.5, '2', 0.5, 'HSA Drawdown'),
    '11B. Tax Capacity':           _spec('2', '1', 8, '1', 8, 'Tax Capacity'),
    '12. Charitable Giving':       _spec('2', '2', 5, '2', 5, 'Charitable Giving', 'charitable_giving'),
    '12B. Tax-Loss Harvesting':    _spec('2', '2', 7, '2', 8, 'Tax-Loss Harvesting', 'tax_loss_harvesting'),
    '12C. Gain Harvesting':        _spec('2', '2', 8, '2', 13, 'Gain Harvesting', 'gain_harvesting'),
    '13. State Residency':         _spec('2', '2', 2, '2', 2, 'State Residency', 'state_residency'),
    '14. Estate Plan':             _spec('2', '2', 6, '2', 6, 'Estate & Legacy Planning', 'estate_legacy_plan'),
    '15. Market-Luck Stress Test': _spec('3', '3', 0, '3', 0, 'Monte Carlo', 'market_luck_stress_test'),
    '16. Scenario Analysis':       _spec('H', module_key='what_if_analysis'),
    '17. LTC Stress Test':         _spec('3', module_key='long_term_care_stress'),
    '18. Survivor Stress Test':    _spec('3', '3', 1, '3', 1, 'Survivor', 'survivor_stress_test'),
    '19. Life Insurance':          _spec('3', '3', 2, '3', 2, 'LTC + Life Insurance', 'life_insurance_need'),
    '20. RMD Audit':               _spec('4', '4', 5, '4', 4, 'RMD Audit', 'rmd_audit'),
    '21. Quality Control':         _spec('4', '4', 4, '4', 3, 'Quality Control'),
    '22. Glossary':                _spec('4', '4', 7, '4', 6, 'Glossary', 'glossary'),
    '23. Methodology':             _spec('4', '4', 6, '4', 5, 'Methodology', 'methodology_rerun'),
    '24. Asset Location':          _spec('2'),
    '25. Account Reconciliation':  _spec('4', '4', 3, '4', 2, 'Account Reconciliation'),
    '26. Workbook Warnings':       _spec('H'),
    '27. Planning Levers':         _spec('4', '4', 7.5, '4', 7.5, 'Planning Levers'),
    '29. Spending Summary':        _spec('1', '1', 6, '1', 6, 'Spending Summary'),
    '30. Education Funding':       _spec('2', '2', 9, '2', 9, 'Education Funding', 'education_funding_529'),
    '31. Existing Life Insurance': _spec('2', '3', 3, '3', 3, 'Existing Life Insurance', 'existing_life_insurance'),
    '32. Disability Income':       _spec('2', '3', 4, '3', 4, 'Disability Income', 'disability_income_insurance'),
    '33. P&C Umbrella':            _spec('2', '3', 5, '3', 5, 'P&C Umbrella', 'property_casualty_umbrella'),
    '34. Business Succession':     _spec('2', '2', 12, '2', 12, 'Business Succession', 'business_succession'),
    '35. Equity Compensation':     _spec('2', '2', 10, '2', 10, 'Equity Compensation', 'equity_compensation'),
    '36. Special-Needs Planning':  _spec('2', '2', 11, '2', 11, 'Special-Needs Planning', 'special_needs_planning'),
    '37. Current vs Proposed':     _spec('1', '1', 7, '1', 7, 'Current vs. Proposed'),
    # 2026-09-09 housing-estimate design, §7.0 H7: the three-axis housing
    # trajectory sweep -- see src/housing_comparison.py.
    # section_rank/letter_rank 17/15 sit right
    # after '11B. Tax Capacity' (16/14), the highest currently used in
    # section '2'/letter_prefix '2', without renumbering anything else.
    # Kept short ("Comparison", not "Trajectory Comparison") because a
    # build-time sheet TITLE is a real openpyxl worksheet name, capped at 31
    # characters -- "38. Housing Trajectory Comparison" (33 chars) tripped
    # that limit.
    '38. Housing Comparison':      _spec('2', '2', 17, '2', 15, 'Housing Comparison', 'housing_trajectory_comparison'),
}

# OPTIONAL_MODULE_SHEETS maps each client_optional_functions.csv toggle key to
# the legacy build-time sheet name(s) it owns, derived from SHEET_REGISTRY.
# workbook_builder skips both the computation and the build_sheetN() call when
# a module is disabled, and prunes the final workbook layout so section
# dividers never link to a removed sheet. Keys with module_key=None are
# always-on core sheets (Executive Summary, Balance Sheet, Cash Flow, Asset
# Allocation, Planning Levers, QC, Plan Data, …) and are never dropped.
OPTIONAL_MODULE_SHEETS: Dict[str, List[str]] = {}
for _sheet_name, _sheet_spec in SHEET_REGISTRY.items():
    if _sheet_spec.module_key:
        OPTIONAL_MODULE_SHEETS.setdefault(_sheet_spec.module_key, []).append(_sheet_name)
del _sheet_name, _sheet_spec


def _force_disabled(key):
    """True iff ``key`` is explicitly named in RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES."""
    forced_off = os.environ.get('RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES', '')
    if not forced_off:
        return False
    k = str(key).strip().lower()
    return k in {m.strip().lower() for m in forced_off.split(',') if m.strip()}


def _base_enabled(c, key):
    """Raw toggle state for ``key`` from env overrides + saved ``c['opt']``.

    This is the pre-Phase-2 gating logic, WITHOUT prerequisite auto-selection.
    Absent keys default to enabled so always-on core sheets are never dropped.
    """
    k = str(key).strip().lower()
    if _force_disabled(key):
        return False
    forced_on = os.environ.get('RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES', '')
    if forced_on:
        if k in {m.strip().lower() for m in forced_on.split(',') if m.strip()}:
            return True
    if os.environ.get('RETIREMENT_SYSTEM_FORCE_ALL_MODULES') == '1':
        return True
    opt = (c or {}).get('opt') or {}
    if key in opt:
        return bool(opt[key])
    for kk, vv in opt.items():
        if str(kk).strip().lower() == k:
            return bool(vv)
    return True


def effective_enabled_modules(c):
    """Optional module keys that should be treated as ON, after Phase-2
    prerequisite auto-selection.

    The set is: every *directly* enabled optional module (per :func:`_base_enabled`)
    PLUS the transitive prerequisite *outputs* each one needs — restricted to
    keys the build-time gate actually knows (:data:`OPTIONAL_MODULE_SHEETS`).

    Rationale: a user who enables a dependent output (e.g. ``life_insurance_need``)
    but forgets its prerequisite (``survivor_stress_test``) would otherwise get a
    broken/empty sheet. Auto-selecting the prerequisite closes that gap.

    Only optional prerequisites need action here — core prerequisites
    (``net_worth``, ``cash_flow``, ``asset_allocation``, …) carry no toggle and
    are always on. A prerequisite that is itself optional gets force-enabled,
    UNLESS it is explicitly named in RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES,
    which always wins (see :func:`module_enabled` precedence).
    """
    enabled = {k for k in OPTIONAL_MODULE_SHEETS if _base_enabled(c, k)}
    auto = set()
    for key in enabled:
        if key not in CATALOG:
            continue
        for dep in prerequisite_outputs(key):
            # Only auto-enable keys the gate knows and that aren't explicitly
            # force-disabled. Core prerequisites aren't in OPTIONAL_MODULE_SHEETS
            # and need no action (they're always on).
            if dep in OPTIONAL_MODULE_SHEETS and not _force_disabled(dep):
                auto.add(dep)
    return enabled | auto


def module_status(c):
    """Per-module gating status for the Optional Modules settings UI.

    Returns ``{key: {"enabled": bool, "auto_enabled": bool, "required_by": [str, ...]}}``
    for every key in :data:`OPTIONAL_MODULE_SHEETS`. This is UI-facing: a settings
    page can show a toggle that reads OFF in ``client_optional_functions.csv`` but
    is still building because Phase-2 prerequisite auto-selection (see
    :func:`effective_enabled_modules`) pulled it in as a dependency of some other
    directly-enabled module — this function is how the UI explains "why is this on
    when I turned it off?" instead of leaving that invisible.

      * ``enabled`` — the final build-time state (delegates to :func:`module_enabled`,
        so precedence/env-override logic lives in exactly one place).
      * ``auto_enabled`` — True only when the module is on *solely* because it's a
        prerequisite of something else, i.e. its own toggle is not directly on.
      * ``required_by`` — the directly-enabled optional module key(s) whose
        prerequisite chain (per :func:`prerequisite_outputs`) includes this key.
        Empty when nothing depends on it.
    """
    eff = effective_enabled_modules(c)
    direct = {k for k in OPTIONAL_MODULE_SHEETS if _base_enabled(c, k)}

    # Reverse lookup: for each directly-enabled module, find which of its
    # prerequisite outputs is `key`.
    required_by_map: dict = {k: [] for k in OPTIONAL_MODULE_SHEETS}
    for enabled_key in direct:
        try:
            deps = prerequisite_outputs(enabled_key)
        except Exception:
            continue
        for dep in deps:
            if dep in required_by_map:
                required_by_map[dep].append(enabled_key)

    status = {}
    for key in OPTIONAL_MODULE_SHEETS:
        auto = (key in eff) and (key not in direct)
        status[key] = {
            "enabled": module_enabled(c, key),
            "auto_enabled": bool(auto),
            "required_by": required_by_map.get(key, []),
        }
    return status


def module_enabled(c, key):
    """True unless the optional-module toggle ``key`` is disabled AND unneeded.

    Reads the ``_b``-normalized booleans loaded into ``c['opt']`` from
    client_optional_functions.csv.  Absent keys default to enabled so always-on
    core sheets are never dropped.

    Env overrides make module gating deterministic for tests (a module named in
    FORCE_DISABLE always wins, so an explicit "off" beats any force-on):
      * RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES="a,b,c" forces the listed module
        keys off regardless of the saved toggles (used by the gating test).
      * RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES="a,b,c" forces the listed module
        keys on. The canonical structural-test fixture lists the classic
        sheet-owning modules here so its "all sheets present" assertions stay
        stable regardless of saved toggles, without force-enabling newer
        default-off modules whose sheets those tests don't expect.
      * RETIREMENT_SYSTEM_FORCE_ALL_MODULES=1 forces every module on.

    Phase-2 prerequisite auto-selection: a disabled optional module that is a
    prerequisite output of an *enabled* optional module is treated as enabled
    anyway, so its dependent module isn't left with a broken/empty sheet (e.g.
    enabling ``life_insurance_need`` pulls in ``survivor_stress_test``).

    Precedence (highest first):
      1. FORCE_DISABLE on the directly-named ``key`` — always off, even if some
         enabled module lists it as a prerequisite.
      2. Directly enabled (FORCE_ENABLE / FORCE_ALL / saved toggle / default-on).
      3. Auto-selected as a prerequisite of an enabled optional module.
      4. Otherwise off.
    """
    # (1) A directly-named FORCE_DISABLE always wins, even over auto-selection.
    if _force_disabled(key):
        return False
    # (2) Direct enablement (env force-on, saved toggle, or default-on).
    if _base_enabled(c, key):
        return True
    # (3) Prerequisite auto-selection: force-enable a disabled optional module
    # that an enabled optional module depends on.
    eff = effective_enabled_modules(c)
    if key in eff:
        return True
    k = str(key).strip().lower()
    if any(str(e).strip().lower() == k for e in eff):
        return True
    # (4) Explicitly disabled and needed by nothing enabled.
    return False


def resolve_selection(selected: List[str]) -> Dict[str, object]:
    """Expand a user selection of outputs into everything needed to run them.

    Returns a dict with:

    * ``outputs`` — the selected keys plus every transitive prerequisite output
      (the auto-selection the UI should apply), demand-ordered.
    * ``input_modules`` — the set of input-module ids those outputs require.
    * ``input_elements`` — {input_module_id: sorted list of specific elements}
      aggregated across the resolved outputs, so the UI can reveal exactly the
      input fields that matter.

    Raises KeyError if any selected key is unknown.
    """
    resolved: List[str] = []
    for key in selected:
        if key not in CATALOG:
            raise KeyError(key)
        for k in (*prerequisite_outputs(key), key):
            if k not in resolved:
                resolved.append(k)

    input_modules: set = set()
    input_elements: Dict[str, set] = {}
    for k in resolved:
        for module_id, elements in CATALOG[k].requires_inputs:
            input_modules.add(module_id)
            if elements:
                input_elements.setdefault(module_id, set()).update(elements)

    resolved.sort(key=lambda k: (DEMAND_RANK[CATALOG[k].demand], CATALOG[k].name))
    return {
        "outputs": resolved,
        "input_modules": sorted(input_modules),
        "input_elements": {m: sorted(v) for m, v in input_elements.items()},
    }


def validate() -> None:
    """Assert the catalog is internally consistent. Called at import time.

    Guards: valid kinds/demands, resolvable & acyclic prerequisites, known input
    ids, unique legacy sheet names, and comparison-mode only on Optimization.
    """
    for key, m in CATALOG.items():
        assert m.key == key, f"catalog key mismatch: {key} != {m.key}"
        assert m.kind in KINDS, f"{key}: bad kind {m.kind!r}"
        assert m.demand in DEMAND_BANDS, f"{key}: bad demand {m.demand!r}"
        assert m.mode in (None, MODE_COMPARISON), f"{key}: bad mode {m.mode!r}"
        if m.mode == MODE_COMPARISON:
            assert m.kind == COMPARISON, f"{key}: comparison mode requires comparison kind"
        for dep in m.requires_outputs:
            assert dep in CATALOG, f"{key}: requires unknown output {dep!r}"
            assert dep != key, f"{key}: requires itself"
        for module_id, _elements in m.requires_inputs:
            assert module_id in INPUT_MODULES, f"{key}: requires unknown input {module_id!r}"
        # (4a) Both axes declared, always. `domain` carries a default only so
        # it can be passed by keyword; omitting it is an error, not a shrug.
        assert m.domain in DOMAINS, (
            f"{key}: domain is {m.domain!r}; every module must declare one of "
            f"{DOMAINS}. kind and domain are independent axes (#330 §4.1) -- "
            f"neither may be derived from the other.")

    # No prerequisite cycles (prerequisite_outputs terminates & excludes self).
    for key in CATALOG:
        deps = prerequisite_outputs(key)
        assert key not in deps, f"{key}: participates in a prerequisite cycle"

    # Legacy sheet names are the stable identity — they must be unique.
    sheets: Dict[str, str] = {}
    for key, m in CATALOG.items():
        if m.sheet is None:
            continue
        assert m.sheet not in sheets, (
            f"duplicate legacy sheet {m.sheet!r} on {key} and {sheets[m.sheet]}")
        # (2) Every catalogued sheet is a registry key. A module naming a sheet
        # the registry has never heard of joins to nothing, and every consumer
        # that walks the join -- gating, sectioning, the switch nav -- silently
        # skips it instead of failing.
        assert m.sheet in SHEET_REGISTRY, (
            f"{key}: sheet {m.sheet!r} is not a SHEET_REGISTRY key, so the "
            f"catalog-to-registry join drops this module silently")
        sheets[m.sheet] = key

    # (3) ...and the reverse: every sheet that reaches the visible nav has a
    # module behind it. A sheet with a `display` and no catalog record cannot
    # be classified, gated, or placed by kind -- which is exactly how HSA
    # Drawdown, Tax Capacity and Current vs Proposed went unrecorded.
    for _name, _spec_ in SHEET_REGISTRY.items():
        if _spec_.display is None:
            continue
        assert _name in sheets, (
            f"sheet {_name!r} appears in the workbook nav but no CATALOG "
            f"module declares it; it cannot be classified or gated")

    # (1) The classification invariant (#329 §3.1). A sheet's letter group is
    # implied by its module's kind, and its section must agree with its letter
    # group. Catches the `2I` and `3D`-`3F` contradictions and every future
    # recurrence, at import time, before anything can be built from them.
    for _name, _spec_ in SHEET_REGISTRY.items():
        if _spec_.letter_prefix is None:
            continue  # hidden/helper sheets are deliberately outside the nav
        _kind = CATALOG[sheets[_name]].kind
        _want = KIND_LETTER_PREFIX[_kind]
        assert _spec_.letter_prefix == _want, (
            f"sheet {_name!r} is kind {_kind!r}, which belongs to letter group "
            f"{_want!r}, but is lettered {_spec_.letter_prefix!r}")
        assert str(_spec_.section) == str(_spec_.letter_prefix), (
            f"sheet {_name!r} sits in section {_spec_.section!r} but is "
            f"lettered {_spec_.letter_prefix!r}; the tab strip and the section "
            f"summary would disagree about where it lives")

    # §7.4: dashboard_step/csv_sections only make sense on a toggleable
    # module, and each step/section must be owned by exactly one module —
    # otherwise step_gate_map()/section_gate_map() would silently drop one.
    steps: Dict[str, str] = {}
    sections: Dict[str, str] = {}
    for key, m in CATALOG.items():
        if m.dashboard_step or m.csv_sections:
            assert m.optional, f"{key}: dashboard_step/csv_sections require optional=True"
        if m.dashboard_step:
            assert m.dashboard_step not in steps, (
                f"dashboard_step {m.dashboard_step!r} claimed by both {key} and {steps[m.dashboard_step]}")
            steps[m.dashboard_step] = key
        for section in m.csv_sections:
            assert section not in sections, (
                f"csv_section {section!r} claimed by both {key} and {sections[section]}")
            sections[section] = key


def summary() -> str:
    """Human-readable one-line-per-kind census (handy for `python -c`)."""
    lines = []
    for kind in KINDS:
        mods = by_kind(kind)
        opt = sum(1 for m in mods if m.optional)
        lines.append(f"{kind:12s} {len(mods):2d} outputs ({opt} optional)  — {KIND_QUESTION[kind]}")
    return "\n".join(lines)


# Fail fast if the catalog is edited into an inconsistent state.
validate()

