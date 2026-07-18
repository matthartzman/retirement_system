"""Module catalog — the single source of truth for the Inputs/Outputs reframing.

This is the codified form of ``documentation/MODULE_REFRAMING_INPUTS_OUTPUTS.md``
(v2). It classifies every workbook output module by the *question it answers*
and records, for each, the inputs and prerequisite outputs it needs plus a
demand band. Later phases (UI page gating, prerequisite auto-selection, section
ordering) consume this instead of the scattered hand-written guards.

Design constraints:

* **Zero heavy dependencies.** This module imports nothing beyond the stdlib so
  it can be loaded and validated without pulling in the reporting/engine stack
  (numpy, openpyxl, …). The legacy ``OPTIONAL_MODULE_SHEETS`` gate in
  ``src.reporting.workbook_common`` stays authoritative for *build-time* sheet
  pruning; this catalog is cross-checked against it by the test-suite, it does
  not replace it.
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
        "core_spending", "Core Spending", PROJECTION, MEDIUM_HIGH,
        "Recurring-spend detail feeding cash flow.",
        sheet="28. Core Spending", tab="1G. Core Spending",
        requires_inputs=(_in("spending", "categories", "housing", "travel", "discretionary"),
                         _in("ytd")),
    ),
    OutputModule(
        "spending_summary", "Spending Summary", PROJECTION, MEDIUM_HIGH,
        "Category roll-up of spend.",
        sheet="29. Spending Summary", tab="1H. Spending Summary",
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
    ),
    OutputModule(
        "tax_loss_harvesting", "Tax-Loss Harvesting", OPTIMIZATION, MEDIUM,
        "Harvestable losses given current lots.",
        sheet="12B. Tax-Loss Harvesting", tab="2I. Tax-Loss Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "charitable_giving", "Charitable Giving", OPTIMIZATION, MEDIUM,
        "Bunching / QCD / DAF strategy and tax effect.",
        optional=True, sheet="12. Charitable Giving", tab="2F. Charitable Giving",
        requires_inputs=(_in("assets", "daf"), _in("income"), _in("household", "age"),
                         _in("assumptions", "brackets")),
    ),
    OutputModule(
        "state_residency", "State Residency", OPTIMIZATION, MEDIUM,
        "Tax impact of relocating.",
        optional=True, sheet="13. State Residency", tab="2C. State Residency",
        requires_inputs=(_in("planning_levers", "residency_choice"), _in("income"),
                         _in("assumptions", "state_tax")),
    ),
    OutputModule(
        "estate_legacy_plan", "Estate & Legacy", OPTIMIZATION, MEDIUM,
        "Estate-tax exposure and legacy/bequest structure.",
        optional=True, sheet="14. Estate Plan", tab="2G. Estate & Legacy Planning",
        requires_inputs=(_in("insurance_estate", "estate_inputs"), _in("assets"),
                         _in("assumptions", "estate_constants")),
    ),
    OutputModule(
        "education_funding_529", "Education Funding 529", OPTIMIZATION, LOW,
        "529 sizing vs education goals.",
        optional=True, sheet="30. Education Funding", tab="2J. Education Funding",
        requires_inputs=(_in("insurance_estate", "529_accounts", "goals"),
                         _in("assumptions", "growth")),
    ),
    OutputModule(
        "equity_compensation", "Equity Compensation", OPTIMIZATION, LOW,
        "RSU / ISO / NSO / ESPP tax and timing.",
        optional=True, sheet="35. Equity Compensation", tab="2K. Equity Compensation",
        requires_inputs=(_in("insurance_estate", "grants"), _in("assumptions", "tax")),
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
    ),
    OutputModule(
        "survivor_stress_test", "Survivor / Early Death", STRESS_TEST, MEDIUM,
        "Plan solvency after one spouse's early death.",
        optional=True, sheet="18. Survivor Stress Test", tab="3B. Survivor",
        requires_inputs=(_in("household", "survivor_state"),
                         _in("income", "survivor_continuation"), _in("insurance_estate")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "long_term_care_stress", "LTC Stress", STRESS_TEST, MEDIUM,
        "Impact of a long-term-care event.",
        optional=True, sheet="17. LTC Stress Test", tab="3C. LTC + Life Insurance",
        requires_inputs=(_in("insurance_estate", "ltc_policy"), _in("assets", "liquidity"),
                         _in("assumptions", "ltc_cost")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "divorce_qdro", "Divorce / QDRO", STRESS_TEST, NICHE,
        "Plan under an imposed asset split (exogenous life event).",
        optional=True, sheet=None, tab=None,
        requires_inputs=(_in("household", "divorce_assumptions"), _in("assets"), _in("holdings")),
        requires_outputs=BASE_PROJECTION,
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

