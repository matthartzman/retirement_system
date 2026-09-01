"""Module catalog — the single source of truth for the Inputs/Outputs reframing.

This is the codified form of ``documentation/MODULE_REFRAMING_INPUTS_OUTPUTS.md``
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
STRESS_TEST = "stress_test"
DIAGNOSTICS = "diagnostics"
REFERENCE = "reference"

KINDS = (PROJECTION, OPTIMIZATION, STRESS_TEST, DIAGNOSTICS, REFERENCE)

KIND_QUESTION = {
    PROJECTION:   "What happens to the plan as-is over time?",
    OPTIMIZATION: "What controllable lever should I change, and by how much?",
    STRESS_TEST:  "Does the plan survive events outside my control?",
    DIAGNOSTICS:  "Is the model itself trustworthy?",
    REFERENCE:    "What inputs and methods produced this?",
}

# High demand → obscure, five bands (ordered most- to least-common).
HIGH = "high"
MEDIUM_HIGH = "medium_high"
MEDIUM = "medium"
LOW = "low"
NICHE = "niche"

DEMAND_BANDS = (HIGH, MEDIUM_HIGH, MEDIUM, LOW, NICHE)
DEMAND_RANK = {band: i for i, band in enumerate(DEMAND_BANDS)}

# ``What-If`` is a *presentation mode* of Optimization, not its own kind.
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
    # ``optional`` mirrors membership in workbook_common.OPTIONAL_MODULE_SHEETS:
    # optional modules carry a client_optional_functions.csv toggle; core
    # modules are always on. ``sheet`` is the legacy build-time sheet name (the
    # stable internal identity used by the gate); ``tab`` is the final
    # presentation label. ``requires_outputs`` are prerequisite output keys.
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
        sheet="5. Net Worth Projection", tab="1B. Net Worth",
        requires_inputs=(_in("household", "ages", "timing"), _in("assets", "balances"),
                         _in("liabilities", "balances"), _in("holdings", "balances"),
                         _in("assumptions", "growth", "cma")),
    ),
    OutputModule(
        "cash_flow", "Cash Flow", PROJECTION, HIGH,
        "Annual inflows/outflows, funding gaps, and withdrawal need.",
        sheet="6. Cash Flow Projection", tab="1C. Cash Flow",
        requires_inputs=(_in("income", "all_streams"), _in("spending", "all"),
                         _in("liabilities", "payments"), _in("household", "ss", "timing")),
    ),
    OutputModule(
        "balance_sheet", "Balance Sheet", PROJECTION, HIGH,
        "Point-in-time assets/liabilities by account and tax type.",
        sheet="3. Balance Sheet", tab="1D. Balance Sheet",
        requires_inputs=(_in("assets"), _in("liabilities"), _in("holdings")),
    ),
    OutputModule(
        "executive_summary", "Executive Summary", PROJECTION, HIGH,
        "One-page KPI roll-up of the whole plan.",
        sheet="1. Executive Summary", tab="1A. Executive Summary",
        requires_outputs=("net_worth", "cash_flow", "balance_sheet"),
    ),
    OutputModule(
        "lifetime_tax_projection", "Lifetime Taxes", PROJECTION, HIGH,
        "Cumulative federal/state/NIIT/IRMAA/payroll/cap-gains over the plan.",
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
        sheet="29. Spending Summary", tab="1G. Spending Summary",
        requires_inputs=(_in("spending"),),
    ),
    OutputModule(
        "charts_dashboard", "Charts", PROJECTION, MEDIUM_HIGH,
        "Visual consolidation of the projection series.",
        optional=True, sheet="8. Charts Dashboard", tab="1E. Charts",
        requires_outputs=("net_worth", "cash_flow", "asset_allocation"),
    ),

    # ── Optimization: decision levers ─────────────────────────────────────────
    OutputModule(
        "roth_conversion_plan", "Roth Conversion", OPTIMIZATION, HIGH,
        "Conversion amounts / bracket-fill; quantifies lifetime tax savings.",
        optional=True, sheet="11. Roth Conversion", tab="2A. Roth Conversion",
        requires_inputs=(_in("planning_levers", "roth_policy", "forced_conversions"),
                         _in("income"), _in("assumptions", "brackets", "irmaa")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="roth_conversion",
    ),
    OutputModule(
        "asset_allocation", "Asset Allocation", OPTIMIZATION, HIGH,
        "Target vs actual mix, drift, and rebalancing guidance.",
        sheet="4. Asset Allocation", tab="2B. Asset Allocation",
        requires_inputs=(_in("planning_levers", "targets", "controls"), _in("holdings"),
                         _in("assumptions", "cma")),
    ),
    OutputModule(
        "social_security_timing", "Social Security", OPTIMIZATION, HIGH,
        "Optimal claiming age; lifetime-benefit comparison.",
        optional=True, sheet="10. Social Security", tab="2D. Social Security",
        requires_inputs=(_in("household", "ss_policy", "dob", "earnings"),
                         _in("planning_levers", "claiming_age")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "retirement_strategy", "Withdrawal Sequencing", OPTIMIZATION, MEDIUM_HIGH,
        "Draw order across account tax types.",
        optional=True, sheet="9. Retirement Strategy", tab="9. Retirement Strategy",
        requires_inputs=(_in("planning_levers", "sequencing"), _in("assets"), _in("holdings")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "asset_location", "Asset Location", OPTIMIZATION, MEDIUM_HIGH,
        "Which assets to hold in which tax bucket.",
        sheet="24. Asset Location", tab="24. Asset Location",
        requires_inputs=(_in("holdings", "lots"), _in("planning_levers", "location_policy"),
                         _in("assumptions", "tax_rates")),
    ),
    OutputModule(
        "what_if_analysis", "What-If / Scenario", OPTIMIZATION, MEDIUM_HIGH,
        "Side-by-side of 2-3 saved lever bundles with deltas (comparison mode).",
        optional=True, sheet="16. Scenario Analysis", tab="16. Scenario Analysis",
        mode=MODE_COMPARISON,
        requires_inputs=(_in("planning_levers", "bundled_positions"),),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="scenarios",
    ),
    OutputModule(
        "tax_loss_harvesting", "Tax-Loss Harvesting", OPTIMIZATION, MEDIUM,
        "Harvestable losses given current lots.",
        optional=True, sheet="12B. Tax-Loss Harvesting", tab="2I. Tax-Loss Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "gain_harvesting", "Gain Harvesting", OPTIMIZATION, MEDIUM,
        "0%-bracket long-term gains harvestable given current lots.",
        optional=True, sheet="12C. Gain Harvesting", tab="2N. Gain Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "charitable_giving", "Charitable Giving", OPTIMIZATION, MEDIUM,
        "Bunching / QCD / DAF strategy and tax effect.",
        optional=True, sheet="12. Charitable Giving", tab="2F. Charitable Giving",
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
        "state_residency", "State Residency", OPTIMIZATION, MEDIUM,
        "Tax impact of relocating.",
        optional=True, sheet="13. State Residency", tab="2C. State Residency",
        requires_inputs=(_in("planning_levers", "residency_choice"), _in("income"),
                         _in("assumptions", "state_tax")),
        dashboard_step="state_residency",
    ),
    OutputModule(
        "estate_legacy_plan", "Estate & Legacy", OPTIMIZATION, MEDIUM,
        "Estate-tax exposure, legacy/bequest structure, beneficiary/titling audit, "
        "gifting schedule, and per-beneficiary 10-year drawdown sensitivity.",
        optional=True, sheet="14. Estate Plan", tab="2G. Estate & Legacy Planning",
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
        optional=True, sheet="30. Education Funding", tab="2J. Education Funding",
        requires_inputs=(_in("insurance_estate", "529_accounts", "goals"),
                         _in("assumptions", "growth")),
        csv_sections=("Education Funding",),
    ),
    OutputModule(
        "equity_compensation", "Equity Compensation", OPTIMIZATION, LOW,
        "RSU / ISO / NSO / ESPP tax and timing.",
        optional=True, sheet="35. Equity Compensation", tab="2K. Equity Compensation",
        requires_inputs=(_in("insurance_estate", "grants"), _in("assumptions", "tax")),
        csv_sections=("Equity Compensation",),
    ),
    OutputModule(
        "scorp_vs_llc", "S-Corp vs LLC", OPTIMIZATION, LOW,
        "Entity-structure tax comparison for the self-employed.",
        sheet="12C. S-Corp vs LLC", tab="2E. S-Corp vs LLC",
        requires_inputs=(_in("income", "self_employment"), _in("business"),
                         _in("assumptions", "tax")),
    ),
    OutputModule(
        "business_succession", "Business Succession", OPTIMIZATION, LOW,
        "Buy-sell / key-person / valuation planning.",
        optional=True, sheet="34. Business Succession", tab="2M. Business Succession",
        requires_inputs=(_in("business", "entity", "valuation", "funding"),),
    ),
    OutputModule(
        "special_needs_planning", "Special-Needs Planning", OPTIMIZATION, NICHE,
        "SNT / ABLE structure for a dependent.",
        optional=True, sheet="36. Special-Needs Planning", tab="2L. Special-Needs Planning",
        requires_inputs=(_in("household", "dependents"), _in("insurance_estate")),
    ),

    # ── Optimization: protection decisions (each requires a Stress result) ────
    OutputModule(
        "life_insurance_need", "Life Insurance Need", OPTIMIZATION, MEDIUM,
        "Coverage to buy vs survivor shortfall — a decision that reads a stress.",
        optional=True, sheet="19. Life Insurance", tab="3C. LTC + Life Insurance",
        requires_inputs=(_in("insurance_estate", "policies"), _in("income")),
        requires_outputs=("survivor_stress_test",),
    ),
    OutputModule(
        "existing_life_insurance", "Existing Life Insurance", OPTIMIZATION, LOW,
        "Adequacy of in-force policies.",
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
        "disability_income_insurance", "Disability Income", OPTIMIZATION, LOW,
        "DI coverage vs income-replacement need.",
        optional=True, sheet="32. Disability Income", tab="3E. Disability Income",
        requires_inputs=(_in("insurance_estate", "di_policies"), _in("income")),
        requires_outputs=("cash_flow",),
    ),
    OutputModule(
        "property_casualty_umbrella", "P&C / Umbrella", OPTIMIZATION, NICHE,
        "Liability coverage adequacy vs net worth.",
        optional=True, sheet="33. P&C Umbrella", tab="3F. P&C Umbrella",
        requires_inputs=(_in("insurance_estate", "pc_policies"),),
        requires_outputs=("net_worth",),
    ),

    # ── Stress test (exogenous events) ────────────────────────────────────────
    OutputModule(
        "market_luck_stress_test", "Monte Carlo", STRESS_TEST, HIGH,
        "Probability of success across market-return paths.",
        optional=True, sheet="15. Market-Luck Stress Test", tab="3A. Monte Carlo",
        requires_inputs=(_in("assumptions", "cma", "correlations"),
                         _in("planning_levers", "mc_settings")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="monte_carlo_options",
    ),
    OutputModule(
        "survivor_stress_test", "Survivor / Early Death", STRESS_TEST, MEDIUM,
        "Plan solvency after one spouse's early death.",
        optional=True, sheet="18. Survivor Stress Test", tab="3B. Survivor",
        requires_inputs=(_in("household", "survivor_state"),
                         _in("income", "survivor_continuation"), _in("insurance_estate")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="survivor_stress",
    ),
    OutputModule(
        "long_term_care_stress", "LTC Stress", STRESS_TEST, MEDIUM,
        "Impact of a long-term-care event.",
        optional=True, sheet="17. LTC Stress Test", tab="3C. LTC + Life Insurance",
        requires_inputs=(_in("insurance_estate", "ltc_policy"), _in("assets", "liquidity"),
                         _in("assumptions", "ltc_cost")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="ltc_stress",
    ),
    OutputModule(
        "divorce_qdro", "Divorce / QDRO", STRESS_TEST, NICHE,
        "Plan under an imposed asset split (exogenous life event).",
        optional=True, sheet=None, tab=None,
        requires_inputs=(_in("household", "divorce_assumptions"), _in("assets"), _in("holdings")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="divorce_options",
    ),

    # ── Diagnostics ──────────────────────────────────────────────────────────
    OutputModule(
        "quality_control", "Quality Control", DIAGNOSTICS, MEDIUM,
        "Pass/fail checks on the projection's internal consistency.",
        sheet="21. Quality Control", tab="4D. Quality Control",
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "rmd_audit", "RMD Audit", DIAGNOSTICS, MEDIUM,
        "Verifies RMD amounts/timing against tax rules.",
        optional=True, sheet="20. RMD Audit", tab="4E. RMD Audit",
        requires_inputs=(_in("household", "ages"), _in("assumptions", "rmd_tables")),
        requires_outputs=("net_worth",),
    ),
    OutputModule(
        "account_reconciliation", "Account Reconciliation", DIAGNOSTICS, MEDIUM,
        "Reconciles modeled balances against YTD actuals.",
        sheet="25. Account Reconciliation", tab="4C. Account Reconciliation",
        requires_inputs=(_in("holdings"), _in("ytd", "transactions", "setup")),
    ),

    # ── Reference / Documentation ─────────────────────────────────────────────
    OutputModule(
        "planning_levers_echo", "Planning Levers (echo)", REFERENCE, MEDIUM,
        "Restates the chosen dial positions with their source.",
        sheet="27. Planning Levers", tab="2H. Planning Levers",
        requires_inputs=(_in("planning_levers"),),
    ),
    OutputModule(
        "assumptions_ref", "Assumptions", REFERENCE, MEDIUM,
        "Echoes the economic/tax assumptions used, for auditability.",
        sheet="2. Assumptions", tab="4B. Assumptions",
        requires_inputs=(_in("assumptions"),),
    ),
    OutputModule(
        "plan_data_ref", "Plan Data", REFERENCE, MEDIUM,
        "Snapshot of all inputs behind the run.",
        sheet="4A. Plan Data", tab="4A. Plan Data",
        requires_inputs=tuple(_in(m) for m in ALL_INPUTS),
    ),
    OutputModule(
        "methodology_rerun", "Methodology & Re-Run", REFERENCE, LOW,
        "Explains the model and how to reproduce the run.",
        optional=True, sheet="23. Methodology", tab="4F. Methodology",
    ),
    OutputModule(
        "glossary", "Glossary", REFERENCE, LOW,
        "Defines terms used across the workbook.",
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
#                    letter_rank -- e.g. '27. Planning Levers' physically sits
#                    in section '4' but is lettered as if it were in '2'.
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
    '11B. Tax Capacity':           _spec('2', '2', 16, '2', 14, 'Tax Capacity'),
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
    '27. Planning Levers':         _spec('4', '4', 2, '2', 7, 'Planning Levers'),
    '29. Spending Summary':        _spec('1', '1', 6, '1', 6, 'Spending Summary'),
    '30. Education Funding':       _spec('2', '2', 9, '2', 9, 'Education Funding', 'education_funding_529'),
    '31. Existing Life Insurance': _spec('2', '2', 13, '3', 3, 'Existing Life Insurance', 'existing_life_insurance'),
    '32. Disability Income':       _spec('2', '2', 14, '3', 4, 'Disability Income', 'disability_income_insurance'),
    '33. P&C Umbrella':            _spec('2', '2', 15, '3', 5, 'P&C Umbrella', 'property_casualty_umbrella'),
    '34. Business Succession':     _spec('2', '2', 12, '2', 12, 'Business Succession', 'business_succession'),
    '35. Equity Compensation':     _spec('2', '2', 10, '2', 10, 'Equity Compensation', 'equity_compensation'),
    '36. Special-Needs Planning':  _spec('2', '2', 11, '2', 11, 'Special-Needs Planning', 'special_needs_planning'),
    '37. Current vs Proposed':     _spec('1', '1', 7, '1', 7, 'Current vs. Proposed'),
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
            assert m.kind == OPTIMIZATION, f"{key}: comparison mode requires optimization kind"
        for dep in m.requires_outputs:
            assert dep in CATALOG, f"{key}: requires unknown output {dep!r}"
            assert dep != key, f"{key}: requires itself"
        for module_id, _elements in m.requires_inputs:
            assert module_id in INPUT_MODULES, f"{key}: requires unknown input {module_id!r}"

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
        sheets[m.sheet] = key

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

