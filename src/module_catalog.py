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

# ── Gate kinds (#330 §5.3, W6) ───────────────────────────────────────────────
# HOW a module is switched on, which is a different question from what it
# produces (`kind`) or what it concerns (`domain`).
#
#   module_toggle — a build-gating boolean in client_optional_functions.csv.
#                   The switch lives on Plan Features; `gate_ref` is None
#                   because the module key IS the toggle's identity.
#   plan_flag     — an ordinary plan row that other rows are semantically
#                   nested under, and which lives beside the fields it
#                   governs (HELOC's flag sits with the credit limit and the
#                   draw-year). The switch renders where its data is, never on
#                   Plan Features, so there is one writer per value.
#
# The two must stay distinct at the point of STORAGE -- a plan flag is plan
# data and travels with the household's CSV, a module toggle is a build
# preference -- and unified at the point of USE, which is what this pair of
# fields buys: `stepGatedByOptionalModule()` no longer needs to know which
# mechanism gates a step, only that the catalog declares one.
GATE_MODULE_TOGGLE = "module_toggle"
GATE_PLAN_FLAG = "plan_flag"
GATE_KINDS = (GATE_MODULE_TOGGLE, GATE_PLAN_FLAG)

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
# (module_key, what this module loses when that module is off). The second half
# is a noun phrase that reads inside "Turning X off also removes ___" -- see
# OutputModule.degrades_without and _soft() below.
SoftDependency = Tuple[str, str]


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
    # ── #330 §3.4: the two relationships ``requires_outputs`` cannot express ──
    #
    # ``requires_outputs`` says exactly one thing: *B cannot run without A*, and
    # ``effective_enabled_modules()`` acts on it by auto-enabling A. Two real
    # relationships in this codebase are not that shape, and were invisible to
    # the catalog until now.
    #
    # ``degrades_without`` — a SOFT dependency. This module still builds when
    # the named module is off; it just says less (Exec Summary drops its Monte
    # Carlo headline rows, Charts drops the fan chart). Auto-enabling would be
    # wrong here, which is why this is a separate field rather than a flag on
    # ``requires_outputs``: nothing in the resolver reads it, by design. It is
    # consumed in both directions —
    #   forward:  "this output shows less because X is off", on the dependent;
    #   reverse:  the warning on X's own switch that names everything X's
    #             removal quietly takes with it ("Turning Monte Carlo off also
    #             removes the success-probability headline from Executive
    #             Summary and the fan chart from Charts"). #330 calls the
    #             reverse direction the single highest-value thing the field
    #             buys, because it is the question a user has *at the switch*.
    # See ``soft_dependents()`` for the reverse map.
    #
    # ``engine_participation`` — True when this module's toggle changes the
    # projection itself, not merely which sheets get written. Today exactly
    # three modules are read by the engine/tax layer directly
    # (``deterministic_engine.py``'s ``equity_compensation`` and
    # ``disability_income_insurance``, ``after_tax.py``'s
    # ``business_succession``). It drives a stronger toggle confirmation in the
    # UI, and it is what makes #330 §3.1's F3 checkable rather than
    # aspirational. W7 fixes the engine's toggle-read *bypass* (it reads raw
    # ``c['opt']`` instead of ``module_enabled()``); this field survives that
    # fix and then describes intended behavior rather than a divergence.
    degrades_without: Tuple[SoftDependency, ...] = field(default_factory=tuple)
    engine_participation: bool = False
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
    # ── #330 §5.3 (W6): how this module is switched on ──────────────────────
    #
    # ``gate_kind`` is GATE_MODULE_TOGGLE (the default, and what every
    # client_optional_functions.csv module is) or GATE_PLAN_FLAG.
    #
    # ``gate_ref`` is None for a module toggle -- the key is the toggle -- and
    # the ``(section, subsection, label)`` triple naming the plan row for a
    # plan flag. It is the exact argument list the frontend's
    # ``sectionFlagEnabled()`` takes, so the JS gate resolves from the
    # declaration instead of a hand-written ``if``.
    #
    # ``gate_enable_label`` is that row's DISPLAY name, which is not derivable
    # from its CSV label (``heloc_enabled`` renders as "Enable HELOC
    # Strategy"). It exists so the "where do I turn this on" note can name the
    # click-path the user will actually see; without it the note would either
    # hand-type the path again in JS -- the twin this field removes -- or show
    # a raw CSV label.
    gate_kind: str = GATE_MODULE_TOGGLE
    gate_ref: Optional[Tuple[str, str, str]] = None
    gate_enable_label: Optional[str] = None
    # ── #330 §3.3 (W8b): one switch, several modules ───────────────────────
    #
    # ``gated_by`` names the module whose toggle decides this one. Everything
    # else about the member stays normal -- it keeps its own key, its own
    # sheet, its own `module_key` in SHEET_REGISTRY, and its own entry in
    # OPTIONAL_MODULE_SHEETS -- so the build gate, the prerequisite resolver
    # and the catalog-to-registry join need no special case at all. The single
    # place that knows about bundles is :func:`_base_enabled`, which reads the
    # PARENT's toggle when a member is asked about. That is deliberate and it
    # is the W7 lesson applied in advance: put the resolution inside the
    # accessor every call site already goes through, and no call site can
    # forget it.
    #
    # It exists because #330 §3.3 resolves Spending Tracker / YTD,
    # `spending_summary` and `account_reconciliation` to ONE switch: all three
    # are YTD-dependent, "a household not tracking transactions has no use for
    # either and neither can compute without the other's data". Two toggles
    # that must always agree are not two features; they are one feature with a
    # way to get into an incoherent state.
    #
    # A member carries NO client_optional_functions.csv row of its own -- the
    # parent's row is its switch, and a second row would be the same double
    # gate #330 Q2 removed from DAF, arriving from the data side.
    # `test_every_optional_module_has_a_toggle_row` enforces both halves.
    #
    # Bundles are one level deep by construction: `validate()` rejects a
    # `gated_by` pointing at a module that is itself `gated_by` something, so
    # the accessor's one-hop resolution is always the whole answer.
    gated_by: Optional[str] = None


def _in(module: str, *elements: str) -> RequiredInput:
    return (module, tuple(elements))


def _soft(module: str, loses: str) -> SoftDependency:
    """A soft dependency and, in the same breath, what it costs.

    ``loses`` is the noun phrase that completes the reverse-direction warning
    on ``module``'s switch: "Turning Monte Carlo off also removes *the
    success-probability headline* from Executive Summary". Written here, next
    to the dependency itself, so the relation and its consequence cannot drift
    apart into two tables.
    """
    return (module, loses)


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
        # spending_tracker.py's budget index lets an Auto policy's real premium
        # supersede the hand-maintained auto_insurance budget line, but only
        # when Existing Life Insurance is on (that module is the gate on every
        # Insurance In Force row). Off, the budget silently falls back to the
        # typed figure -- less accurate, still a cash flow.
        degrades_without=(_soft("existing_life_insurance",
                              "the real auto-policy premium behind the auto-insurance budget line"),),
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
        # Two headline blocks are suppressed rather than zeroed when their
        # module is off: the Monte Carlo rows (worst-case ending wealth, model
        # risk rating) and the Social Security claim-age line.
        degrades_without=(_soft("market_luck_stress_test", "the success-probability headline"),
                          _soft("social_security_timing", "the optimal claim-age line")),
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
        #
        # #330 §3.3 retracted the "must stay core" verdict on this module and
        # W8b implements the retraction: reading the builder shows the sheet is
        # the *YTD spending tracker's* summary (its title renders as
        # "SPENDING SUMMARY — {year} YTD ({days} days elapsed)" and its body
        # comes from transaction tracking types), so the #221 reconciliation it
        # carries is tracker output, not a plan-wide correctness check. It is
        # near-empty without YTD data, which is the same condition that made
        # `account_reconciliation` optional -- hence one switch over both,
        # `gated_by` the tracker rather than a toggle of its own.
        "spending_summary", "Spending Summary", PROJECTION, MEDIUM_HIGH,
        "Category roll-up of spend, including a Core Expenses vs. modeled-assumption reconciliation.",
        domain=SPENDING,
        optional=True, gated_by="spending_tracker_ytd",
        sheet="29. Spending Summary", tab="1G. Spending Summary",
        requires_inputs=(_in("spending"),),
    ),
    OutputModule(
        # ── #330 §3.3 (W8b): the bundle parent ───────────────────────────────
        #
        # Registry gap closed. The Spending Tracker / YTD workflow behaves like
        # a feature and was never catalogued: `spending_tracker.py`, the YTD
        # input pages, and `ytd_blend_enabled` -- #330 §2.3 files it as "a
        # modeling option gating a whole workflow -- the one genuine borderline
        # case in §2.1's taxonomy", and §3.2 gives it the largest off-surface
        # of the twelve newly-optional candidates.
        #
        # It owns NO workbook sheet of its own. What it owns is the two sheets
        # that are its output (`spending_summary`, `account_reconciliation`,
        # both `gated_by` this key) and the current-year blend in
        # `ytd_projection_blend.py`. That is why it is the parent rather than a
        # third peer: the other two are things the tracker produces, not
        # features a household would want independently of it.
        #
        # `kind` is PROJECTION, and that was a judgment call (recorded in W8b's
        # notes doc). The tracker is an *ingest* workflow, which no kind names;
        # of the eight, PROJECTION's question -- "What happens to the plan as-is
        # over time?" -- is the one its switch actually answers, because what
        # the toggle changes is whether real YTD actuals are blended into the
        # current year's projection. DIAGNOSTICS ("Is the model itself
        # trustworthy?") describes `account_reconciliation`, which is one of
        # its outputs, not the tracker. Kind is unconstrained here in practice:
        # validate()'s letter-group invariant only binds modules that own a
        # registry sheet, and this one does not.
        "spending_tracker_ytd", "Spending Tracker / YTD", PROJECTION, MEDIUM_HIGH,
        "Tracks this year's real income and spending transactions and blends them "
        "into the current-year projection; the switch behind Spending Summary and "
        "Account Reconciliation.",
        domain=SPENDING,
        optional=True,
        requires_inputs=(_in("ytd", "transactions", "setup"), _in("spending")),
        # The toggle moves the projection, not merely which sheets are written:
        # `ytd_projection_blend.py` blends real current-year flows into the
        # current year when this is on. Flagged so #330 §3.1's F3 stays
        # checkable, and so the UI gives the switch its stronger confirmation.
        engine_participation=True,
    ),
    OutputModule(
        "charts_dashboard", "Charts", PROJECTION, MEDIUM_HIGH,
        "Visual consolidation of the projection series.",
        domain=INVESTMENTS,
        optional=True, sheet="8. Charts Dashboard", tab="1E. Charts",
        requires_outputs=("net_worth", "cash_flow", "asset_allocation"),
        # The percentile-band ("fan") chart is embedded only when Monte Carlo
        # ran; the rest of the dashboard is unaffected.
        degrades_without=(_soft("market_luck_stress_test", "the fan chart"),),
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
        # W8b: Sheet 11 carries one sentence pointing the reader at the HSA
        # drawdown schedule's own tab (rendered only in `optimize` mode). With
        # `hsa_drawdown` newly toggleable that tab can be absent while the mode
        # still says `optimize`, so the pointer is suppressed rather than left
        # naming a sheet the workbook does not contain. Soft, not hard: Sheet
        # 11's own analysis is identical either way.
        degrades_without=(_soft("hsa_drawdown",
                                "the pointer to the HSA drawdown schedule's own tab"),),
        dashboard_step="roth_conversion",
    ),
    OutputModule(
        # Registry gap closed (#329 §2.1): a textbook plan optimizer — it
        # enumerates drawdown orders, scores them and ranks — that had a sheet
        # and a builder but no catalog record, so nothing could reason about
        # it. W8b (#330 P6b) makes it toggleable.
        #
        # The toggle stops at the sheet, deliberately. #330 §3.2's off-column
        # reads "Sheet not built; `hsa_withdrawal_mode` stops being honored",
        # and only the first half is implemented here. `hsa_withdrawal_mode`
        # is a *planning lever* the household sets on Planning Levers, read by
        # `planning_engines.withdraw_hsa_window` and by
        # `workbook_builder._ensure_hsa_schedule_file`; letting a feature
        # switch suppress it would put a second, invisible gate on a
        # calculation lever -- the same double-gate shape #330 Q2 removed from
        # DAF -- and would leave `mode == 'optimize'` matching no engine
        # branch at all rather than falling back to a named mode. So
        # `engine_participation` stays False and stays true: turning this
        # module off removes the analysis sheet, not the drawdown the plan
        # models. (Recorded in W8b's notes doc, not decided silently.)
        "hsa_drawdown", "HSA Drawdown", OPTIMIZATION, MEDIUM,
        "Drawdown order for HSA dollars; self-gates on hsa_withdrawal_mode == 'optimize'.",
        domain=TAXES,
        optional=True,
        sheet="11C. HSA Drawdown", tab="2B. HSA Drawdown",
        requires_inputs=(_in("planning_levers", "hsa_withdrawal_mode"),
                         _in("assets"), _in("assumptions", "brackets")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        # Registry gap closed (#329 §2.1). Filed under Optimizers, but by its
        # own docstring it "derives nothing new" — every column reads a value
        # the engine or another sheet already computed.
        #
        # Kind is REFERENCE, not WORKSHEET, though it computes nothing new
        # like `current_vs_proposed` does: placement, not shape, decided this.
        # W0/V3 first read Reports; overridden by explicit direction to file
        # it in System instead, alongside Plan Data/Assumptions/Methodology/
        # Glossary. WORKSHEET's letter group (kind_letter_prefix, below) is
        # Reports; REFERENCE's is System, so the kind carries the placement
        # rather than a hand-typed section field duplicating it. `domain`
        # (Taxes, #330 §4.2) is unaffected -- that axis is independent of
        # which workbook group the sheet letters into.
        "tax_capacity", "Tax Capacity", REFERENCE, MEDIUM,
        "Consolidated per-year bracket, IRMAA and ACA headroom, assembled from four other sheets.",
        domain=TAXES,
        optional=True,
        sheet="11B. Tax Capacity", tab="5I. Tax Capacity",
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
        optional=True, sheet="10. Social Security", tab="2D. Social Security",
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
        optional=True,
        sheet="24. Asset Location", tab="24. Asset Location",
        requires_inputs=(_in("holdings", "lots"), _in("planning_levers", "location_policy"),
                         _in("assumptions", "tax_rates")),
    ),
    OutputModule(
        "what_if_analysis", "What-If / Scenario", COMPARISON, MEDIUM_HIGH,
        "Side-by-side of 2-3 saved lever bundles with deltas (comparison mode).",
        domain=RISK_RESILIENCE,
        optional=True, sheet="16. Scenario Analysis", tab="3C. Scenario Analysis",
        mode=MODE_COMPARISON,
        requires_inputs=(_in("planning_levers", "bundled_positions"),),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="scenarios",
    ),
    OutputModule(
        "tax_loss_harvesting", "Tax-Loss Harvesting", OPTIMIZATION, MEDIUM,
        "Harvestable losses given current lots.",
        domain=TAXES,
        optional=True, sheet="12B. Tax-Loss Harvesting", tab="2H. Tax-Loss Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "gain_harvesting", "Gain Harvesting", OPTIMIZATION, MEDIUM,
        "0%-bracket long-term gains harvestable given current lots.",
        domain=TAXES,
        optional=True, sheet="12C. Gain Harvesting", tab="2I. Gain Harvesting",
        requires_inputs=(_in("holdings", "lots", "basis"), _in("pricing")),
    ),
    OutputModule(
        "charitable_giving", "Charitable Giving", OPTIMIZATION, MEDIUM,
        "Bunching / QCD / DAF strategy and tax effect.",
        domain=TAXES,
        optional=True, sheet="12. Charitable Giving", tab="2E. Charitable Giving",
        # QCD (item 4.1) and DAF-appreciated-securities (item 4.2) fields
        # landed in Wave 4, after this entry was first authored — added here
        # as the Wave 3.5a rework the review's own §9.1 called for ("new
        # modules should be authored against the reframed registry, not
        # retrofitted into it").
        requires_inputs=(_in("assets", "daf", "daf_appreciated_securities"),
                         _in("spending", "qcd"), _in("income"),
                         _in("household", "age"), _in("assumptions", "brackets")),
        # #330 Q2 (W6): `csv_sections=("DAF",)` was dropped here. DAF was
        # double-gated -- by this module's toggle AND by its own plan flag --
        # and QCD, which is the same feature from the other side, was gated by
        # its plan flag alone. QCD *cannot* have a section gate: its rows live
        # in the shared `Cashflow` section, which section gating would take out
        # wholesale. So DAF was the anomaly, and the plan flag owns it now, as
        # the `daf_giving` entry below declares. No user-set row is deleted by
        # the change; DAF rows simply stop disappearing when this module is off.
        dashboard_step="entity_charitable",
    ),
    OutputModule(
        "state_residency", "State Residency", COMPARISON, MEDIUM,
        "Tax impact of relocating.",
        domain=HOUSING_PROPERTY,
        optional=True, sheet="13. State Residency", tab="3A. State Residency",
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
        optional=True, sheet="38. Housing Comparison", tab="2G. Housing Comparison",
        requires_inputs=(_in("household", "next_housing_steps"), _in("assumptions", "growth")),
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "estate_legacy_plan", "Estate & Legacy", OPTIMIZATION, MEDIUM,
        "Estate-tax exposure, legacy/bequest structure, beneficiary/titling audit, "
        "gifting schedule, and per-beneficiary 10-year drawdown sensitivity.",
        domain=ESTATE_LEGACY,
        optional=True, sheet="14. Estate Plan", tab="2F. Estate & Legacy Planning",
        # Account titling (4.7), gifting schedule (4.8), and the per-beneficiary
        # drawdown (4.9) all shipped in Wave 4, after this entry was first
        # authored, and landed as new sections on this same sheet rather than
        # new catalog entries of their own (edit-only CSV sections, no
        # dedicated dashboard step yet) - added here as the Wave 3.5a rework
        # the review's own §9.1 called for.
        requires_inputs=(_in("insurance_estate", "estate_inputs", "account_titling", "gifting_schedule"),
                         _in("assets"), _in("household", "ages"),
                         _in("assumptions", "estate_constants")),
        # Deliberately NOT degrades_without=("business_succession",): with that
        # module off, after_tax.business_taxable_estate_value() returns 0.0 and
        # this sheet's estate-tax base is smaller, but nothing is *removed* --
        # every section still renders. A figure changing is engine
        # participation (declared on business_succession itself), not soft
        # degradation, and conflating the two would make the off-impact warning
        # cry wolf about a number the user cannot see change.
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
        # deterministic_engine.py models grant vest/exercise income and the ISO
        # minimum-tax credit carry only when this is on: the toggle moves the
        # projection's rows, not just whether sheet 35 is written.
        engine_participation=True,
    ),
    OutputModule(
        "scorp_vs_llc", "S-Corp vs LLC", COMPARISON, LOW,
        "Entity-structure tax comparison for the self-employed.",
        domain=FAMILY_BUSINESS,
        optional=True,
        sheet="S-Corp vs LLC", tab="3B. S-Corp vs LLC",
        requires_inputs=(_in("income", "self_employment"), _in("business"),
                         _in("assumptions", "tax")),
    ),
    OutputModule(
        "business_succession", "Business Succession", OPTIMIZATION, LOW,
        "Buy-sell / key-person / valuation planning.",
        domain=FAMILY_BUSINESS,
        optional=True, sheet="34. Business Succession", tab="2M. Business Succession",
        requires_inputs=(_in("business", "entity", "valuation", "funding"),),
        # after_tax.business_taxable_estate_value() adds the owner's projected
        # business interest to the taxable estate only when this is on, so the
        # toggle changes computed estate tax, not just sheet 34's existence.
        engine_participation=True,
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
        optional=True, sheet="19. Life Insurance", tab="4D. Life Insurance Need",
        requires_inputs=(_in("insurance_estate", "policies"), _in("income")),
        requires_outputs=("survivor_stress_test",),
    ),
    OutputModule(
        "existing_life_insurance", "Existing Life Insurance", PROTECTION, LOW,
        "Adequacy of in-force policies.",
        domain=ASSETS_PROTECTION,
        optional=True, sheet="31. Existing Life Insurance", tab="4E. Existing Life Insurance",
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
        optional=True, sheet="32. Disability Income", tab="4F. Disability Income",
        requires_inputs=(_in("insurance_estate", "di_policies"), _in("income")),
        requires_outputs=("cash_flow",),
        # deterministic_engine.py models the DI benefit stream from this toggle.
        engine_participation=True,
    ),
    OutputModule(
        "property_casualty_umbrella", "P&C / Umbrella", PROTECTION, NICHE,
        "Liability coverage adequacy vs net worth.",
        domain=ASSETS_PROTECTION,
        optional=True, sheet="33. P&C Umbrella", tab="4G. P&C Umbrella",
        requires_inputs=(_in("insurance_estate", "pc_policies"),),
        requires_outputs=("net_worth",),
    ),

    # ── Stress test (exogenous events) ────────────────────────────────────────
    OutputModule(
        "market_luck_stress_test", "Monte Carlo", STRESS_TEST, HIGH,
        "Probability of success across market-return paths.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="15. Market-Luck Stress Test", tab="4A. Monte Carlo",
        requires_inputs=(_in("assumptions", "cma", "correlations"),
                         _in("planning_levers", "mc_settings")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="monte_carlo_options",
    ),
    OutputModule(
        "survivor_stress_test", "Survivor / Early Death", STRESS_TEST, MEDIUM,
        "Plan solvency after one spouse's early death.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="18. Survivor Stress Test", tab="4B. Survivor",
        requires_inputs=(_in("household", "survivor_state"),
                         _in("income", "survivor_continuation"), _in("insurance_estate")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="survivor_stress",
    ),
    OutputModule(
        "long_term_care_stress", "LTC Stress", STRESS_TEST, MEDIUM,
        "Impact of a long-term-care event.",
        domain=RISK_RESILIENCE,
        optional=True, sheet="17. LTC Stress Test", tab="4C. LTC Stress Test",
        requires_inputs=(_in("insurance_estate", "ltc_policy"), _in("assets", "liquidity"),
                         _in("assumptions", "ltc_cost")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="ltc_stress",
    ),
    OutputModule(
        # #329 §1.2/§3.3 (W9): gained a workbook sheet -- "a UI-only stress
        # test with no workbook counterpart... the mirror image of the
        # workbook-only optimizers." The sheet reuses the exact re-projection
        # Sheet 16 (Scenario Analysis)'s own "Divorce/QDRO Asset Split" row
        # already computes; see build_sheet39 (sheets_stress.py).
        "divorce_qdro", "Divorce / QDRO", STRESS_TEST, NICHE,
        "Plan under an imposed asset split (exogenous life event).",
        domain=RISK_RESILIENCE,
        optional=True, sheet="39. Divorce QDRO Stress Test", tab="4D. Divorce QDRO",
        requires_inputs=(_in("household", "divorce_assumptions"), _in("assets"), _in("holdings")),
        requires_outputs=BASE_PROJECTION,
        dashboard_step="divorce_options",
    ),

    # ── Diagnostics ──────────────────────────────────────────────────────────
    OutputModule(
        "quality_control", "Quality Control", DIAGNOSTICS, MEDIUM,
        "Pass/fail checks on the projection's internal consistency.",
        domain=REPORTS_DOCUMENTATION,
        sheet="21. Quality Control", tab="5D. Quality Control",
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "rmd_audit", "RMD Audit", DIAGNOSTICS, MEDIUM,
        "Verifies RMD amounts/timing against tax rules.",
        domain=TAXES,
        optional=True, sheet="20. RMD Audit", tab="5E. RMD Audit",
        requires_inputs=(_in("household", "ages"), _in("assumptions", "rmd_tables")),
        requires_outputs=("net_worth",),
    ),
    OutputModule(
        # W8b: the other half of #330 §3.3's one-switch bundle. This module
        # already declared `ytd` as a required input -- the only module in the
        # catalog that did -- which is what makes "reconciliation auto-off"
        # (§3.2's off-column) a consequence of the tracker's switch rather than
        # a rule of its own. #330 Q4 refused data-conditional auto-off as a
        # fifth precedence rule on `module_enabled`; `gated_by` gets the same
        # outcome for this pair without touching the precedence ladder at all.
        "account_reconciliation", "Account Reconciliation", DIAGNOSTICS, MEDIUM,
        "Reconciles modeled balances against YTD actuals.",
        domain=REPORTS_DOCUMENTATION,
        optional=True, gated_by="spending_tracker_ytd",
        sheet="25. Account Reconciliation", tab="5C. Account Reconciliation",
        requires_inputs=(_in("holdings"), _in("ytd", "transactions", "setup")),
    ),

    # ── Reference / Documentation ─────────────────────────────────────────────
    OutputModule(
        "planning_levers_echo", "Planning Levers (echo)", REFERENCE, MEDIUM,
        "Restates the chosen dial positions with their source.",
        domain=REPORTS_DOCUMENTATION,
        sheet="27. Planning Levers", tab="5H. Planning Levers",
        requires_inputs=(_in("planning_levers"),),
        # The "Current model anchor" block keeps its Monte Carlo success row
        # (the lever formulas below it reference fixed anchor cells, so the row
        # must not move) but shows "Not run (module off)" in place of a figure.
        degrades_without=(_soft("market_luck_stress_test",
                              "the Monte Carlo success figure in the model anchor"),),
    ),
    OutputModule(
        "assumptions_ref", "Assumptions", REFERENCE, MEDIUM,
        "Echoes the economic/tax assumptions used, for auditability.",
        domain=REPORTS_DOCUMENTATION,
        sheet="2. Assumptions", tab="5B. Assumptions",
        requires_inputs=(_in("assumptions"),),
    ),
    OutputModule(
        "plan_data_ref", "Plan Data", REFERENCE, MEDIUM,
        "Snapshot of all inputs behind the run.",
        domain=REPORTS_DOCUMENTATION,
        sheet="Plan Data", tab="5A. Plan Data",
        requires_inputs=tuple(_in(m) for m in ALL_INPUTS),
    ),
    OutputModule(
        "methodology_rerun", "Methodology & Re-Run", REFERENCE, LOW,
        "Explains the model and how to reproduce the run.",
        domain=REPORTS_DOCUMENTATION,
        optional=True, sheet="23. Methodology", tab="5F. Methodology",
    ),
    OutputModule(
        # Registry gap closed (#330 §7.1). Restates recommendations modeled on
        # other sheets, so it is a WORKSHEET rather than a COMPARISON: the
        # alternatives are not two things the user named, they are this plan
        # before and after the recommendations it already tracks.
        "current_vs_proposed", "Current vs Proposed", WORKSHEET, MEDIUM,
        "Every tracked recommendation, active or proposed, with its cash-flow delta.",
        domain=REPORTS_DOCUMENTATION,
        optional=True,
        sheet="37. Current vs Proposed", tab="1H. Current vs. Proposed",
        requires_outputs=BASE_PROJECTION,
    ),
    OutputModule(
        "glossary", "Glossary", REFERENCE, LOW,
        "Defines terms used across the workbook.",
        domain=REPORTS_DOCUMENTATION,
        optional=True, sheet="22. Glossary", tab="5G. Glossary",
    ),

    # ── Plan-flag features (#330 §5.3, W6) ──────────────────────────────────
    # Catalogued for the same reason every other feature is: so the nav gate,
    # the "where do I turn this on" note and the Plan Features census read one
    # declaration instead of a hand-written branch each. They are NOT
    # ``optional=True``: that field means "carries a client_optional_functions
    # .csv toggle", which these deliberately do not -- their switch is a plan
    # row that travels with the household's data. They own no workbook sheet
    # either, so they never reach the SHEET_REGISTRY join.
    OutputModule(
        "heloc", "HELOC", OPTIMIZATION, LOW,
        "Draw from a home-equity line for large discretionary spending "
        "instead of liquidating portfolio assets.",
        domain=HOUSING_PROPERTY,
        dashboard_step="heloc_strategy",
        gate_kind=GATE_PLAN_FLAG,
        gate_ref=("HELOC", "Setup", "heloc_enabled"),
        gate_enable_label="Enable HELOC Strategy",
    ),
    OutputModule(
        # No dashboard_step, no csv_sections -- unlike HELOC, this flag gates
        # a row GROUP inside Other Assets rather than a page or a shared
        # workbook-input section, via optionalModuleState()'s own
        # `sec === "Hybrid LTC"` branch (dashboard.js). That branch is a
        # THIRD hand-written gate, of the same kind W6 deliberately left
        # alone on HELOC's side (rowsForStep()'s "heloc_strategy" branch, see
        # the notes doc) -- not one of the two the scope line names for
        # removal. Catalogued here so the feature is visible to the taxonomy
        # and the double-gate guard below, without inventing a third gate map
        # this workstream has no consumer for.
        "hybrid_ltc_policy", "LTC/Life Policy", PROTECTION, LOW,
        "A hybrid long-term-care / life policy: premiums, face value and the "
        "benefit it pays against a care event.",
        domain=ASSETS_PROTECTION,
        gate_kind=GATE_PLAN_FLAG,
        gate_ref=("Hybrid LTC", "Settings", "enabled"),
        gate_enable_label="Enabled",
    ),
    OutputModule(
        # DAF and QCD are one feature seen from two sides -- bunch giving for
        # the deduction, or give straight from the IRA -- so they share a
        # domain and differ only in where their rows live. #330 Q2 resolves
        # them identically, and QCD is the one that was already right.
        "daf_giving", "DAF Giving", OPTIMIZATION, LOW,
        "Contribute to a donor-advised fund in a high-income year and grant "
        "from it over later years.",
        domain=ESTATE_LEGACY,
        # Deliberately no csv_sections. The DAF flag's own row lives in the
        # section it would gate, so a section gate here would hide the switch
        # that turns it back on. `entityCharitableGatedRows()` already gates
        # these rows the right way -- showing the enable row and hiding the
        # rest -- which is precisely what QCD has always done.
        gate_kind=GATE_PLAN_FLAG,
        gate_ref=("DAF", "Settings", "enabled"),
        gate_enable_label="Enabled",
    ),
    OutputModule(
        "qcd_giving", "QCD Giving", OPTIMIZATION, LOW,
        "Give directly from an IRA at 70.5+, satisfying required distributions "
        "without the amount landing in taxable income.",
        domain=ESTATE_LEGACY,
        gate_kind=GATE_PLAN_FLAG,
        gate_ref=("Cashflow", "Charitable Giving", "qcd_enabled"),
        gate_enable_label="Enabled",
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
    return {m.dashboard_step: m.key for m in _OUTPUTS
            if m.dashboard_step and m.gate_kind == GATE_MODULE_TOGGLE}


def flag_gate_map() -> Dict[str, Dict[str, object]]:
    """{dashboard_step_id: {...}} for every step gated by a PLAN FLAG (§5.3).

    The sibling of :func:`step_gate_map`, and deliberately a separate map
    rather than more rows in that one: the two are read with different
    predicates on the frontend (``optionalFunctionEnabled(key)`` vs
    ``sectionFlagEnabled(section, subsection, label)``), so merging them would
    only force the caller to re-derive which kind it was holding.

    Each value carries what the frontend needs to both *evaluate* the gate and
    *explain* it:

      * ``key`` / ``name``  — the module's identity and display name.
      * ``ref``             — ``[section, subsection, label]``, exactly the
                              arguments ``sectionFlagEnabled()`` takes.
      * ``enable_label``    — the flag row's display name, for the click-path
                              in the "where do I turn this on" note.

    >>> flag_gate_map()["heloc_strategy"]["ref"]
    ['HELOC', 'Setup', 'heloc_enabled']
    """
    return {
        m.dashboard_step: {
            "key": m.key,
            "name": m.name,
            "ref": list(m.gate_ref or ()),
            "enable_label": m.gate_enable_label,
        }
        for m in _OUTPUTS
        if m.dashboard_step and m.gate_kind == GATE_PLAN_FLAG
    }


def section_gate_map() -> Dict[str, str]:
    """{csv_section: optional_module_key} for every input-CSV section a
    module gates within a step that stays visible regardless (§7.4).
    Replaces the hand-maintained ``ROW_MODULE_GATES`` object in dashboard.js.
    """
    # No plan flag declares csv_sections today (see the hybrid_ltc_policy
    # entry above), so no filter is needed here the way step_gate_map() needs
    # one for flag-gated steps -- but if a future entry adds one, this walks
    # ALL of ``_OUTPUTS`` including plan flags, which would silently report
    # that section permanently off via optionalFunctionEnabled(). Filtering
    # here preemptively, at zero cost while the case doesn't exist, is cheaper
    # than re-discovering the bug step_gate_map() had.
    out: Dict[str, str] = {}
    for m in _OUTPUTS:
        if m.gate_kind != GATE_MODULE_TOGGLE:
            continue
        for section in m.csv_sections:
            out[section] = m.key
    return out


def optional_keys() -> List[str]:
    """Keys of modules that carry a client_optional_functions.csv toggle."""
    return [m.key for m in _OUTPUTS if m.optional]


def core_keys() -> List[str]:
    """Keys of always-on core modules (no switch of any kind).

    W6 narrowed this: a plan-flag module is not optional (it carries no
    client_optional_functions.csv toggle) but it is emphatically not always-on
    either -- HELOC defaults to NO. Reading "not optional" as "core" would
    have quietly promoted every plan flag into the always-on set.
    """
    return [m.key for m in _OUTPUTS
            if not m.optional and m.gate_kind == GATE_MODULE_TOGGLE]


def plan_flag_keys() -> List[str]:
    """Keys of modules switched by a plan-data flag rather than a toggle."""
    return [m.key for m in _OUTPUTS if m.gate_kind == GATE_PLAN_FLAG]


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


def soft_dependents(key: str) -> List[SoftDependency]:
    """``(module, what it loses)`` for everything that degrades without ``key``.

    This is the direction the UI actually asks about. ``degrades_without`` is
    written on the *dependent* ("Exec Summary shows less without Monte Carlo"),
    but the question a user has is at the switch they are about to flip
    ("what does turning Monte Carlo off cost me?"). Inverting it here keeps the
    declaration in the one place a reader of that module will look, and keeps
    the two directions from being hand-maintained separately -- the
    hand-typed-twin problem #329 exists to end.

    Unlike :func:`prerequisite_outputs` this is deliberately NOT transitive:
    soft degradation does not compose (Exec Summary saying less does not make
    whatever reads Exec Summary say less), and it never auto-enables anything.

    Returns catalog-declaration order, so the sentence built from it is stable
    across runs. Empty for a module nothing degrades without -- which is most
    of them.

    >>> soft_dependents("market_luck_stress_test")[0]
    ('executive_summary', 'the success-probability headline')
    """
    if key not in CATALOG:
        raise KeyError(key)
    return [(m.key, loses) for m in _OUTPUTS
            for dep, loses in m.degrades_without if dep == key]


def engine_participants() -> List[str]:
    """Keys whose toggle changes the projection itself (``engine_participation``).

    #330 §3.1's F3 asks whether the engine and the sheets agree about which
    modules are on. This is the list that question is asked *about*; without it
    F3 can only be asserted, not checked.
    """
    return [m.key for m in _OUTPUTS if m.engine_participation]


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
#   slug          -- #329 P2 (W2): the letter-independent stable identity.
#                    Unlike the dict key above (a legacy build-time name that
#                    still carries old V5 numbering, e.g. '11C. HSA
#                    Drawdown') and unlike the final display name (whose
#                    letter shifts with every other toggle, #1.1's
#                    shifting-letters defect), `slug` never changes: not when
#                    a module is added/removed/reordered, not when `display`
#                    is reworded. It is the identity an external ticket,
#                    design doc, or support note should reference instead of
#                    a letter. Required (no default) so a new sheet cannot be
#                    added without picking one; validate() asserts every slug
#                    is unique. workbook_common.compute_final_sheet_renames
#                    dual-keys FINAL_SHEET_RENAMES by both the dict key and
#                    the slug, so `FINAL_SHEET_RENAMES[slug]` always resolves
#                    -- but the in-cell text substitution pass
#                    (_replace_text_refs) still searches for the dict-key
#                    string, not the slug: slugs are short snake_case
#                    fragments ('tax_capacity', 'pc_umbrella') that could
#                    collide with an unrelated internal identifier already
#                    sitting inside existing cell prose, where the long,
#                    punctuated dict-key strings ('11B. Tax Capacity') can't.
SheetSpec = namedtuple(
    'SheetSpec',
    'v5_code section section_rank letter_prefix letter_rank display module_key slug',
)


# The kind -> letter-group map validate() enforces below. #329 §3.1: a sheet's
# workbook group is a CONSEQUENCE of its module's kind, not a second fact typed
# beside it. `_visible()` (below) derives every sheet's `section`/
# `letter_prefix` from this table -- there is no hand-typed twin left for
# validate() to check against; the invariant is now structural.
#
# COMPARISON has its own group ('3. Comparisons'), and PROTECTION joins
# STRESS_TEST under '4. Risks' -- #329 §3.2's regrouping. DIAGNOSTICS and
# REFERENCE take '5' ('5. System'): group '4' is claimed by Risks, and #329
# never named a System section in its own numbering (that section is outside
# its scope; see docs/superpowers/plans/2026-09-21-w3-workbook-regrouping-notes.md).
#
# WORKSHEET shares '1' with PROJECTION deliberately: a worksheet restates
# figures computed elsewhere, which is what a report does (`current_vs_
# proposed`). REFERENCE also restates figures computed elsewhere but files
# in System instead (`tax_capacity`, alongside Plan Data/Assumptions/
# Methodology/Glossary) -- the two kinds exist because the same shape of
# module can be placed in either group, and `domain` (independent of both)
# is what a future UI groups by regardless of which one a sheet lands in.
KIND_LETTER_PREFIX: Dict[str, str] = {
    PROJECTION:   '1',
    WORKSHEET:    '1',
    OPTIMIZATION: '2',
    COMPARISON:   '3',
    PROTECTION:   '4',
    STRESS_TEST:  '4',
    DIAGNOSTICS:  '5',
    REFERENCE:    '5',
}

# Reverse of CATALOG: stable sheet name -> its module's `kind`. Every sheet
# that reaches the visible nav is guaranteed an entry here by validate()'s
# guard (3) below -- a KeyError out of `_group_for` means that guard would
# already have failed.
_SHEET_KIND: Dict[str, str] = {m.sheet: m.kind for m in CATALOG.values() if m.sheet}


def _group_for(sheet_name: str) -> str:
    return KIND_LETTER_PREFIX[_SHEET_KIND[sheet_name]]


def _visible(name, v5_code=None, section_rank=None, letter_rank=None,
             display=None, module_key=None, *, slug):
    """A sheet that appears in the numbered/lettered nav. `section` and
    `letter_prefix` are DERIVED from the sheet's module's `kind` via
    KIND_LETTER_PREFIX -- never hand-typed (#329 F7). `section_rank` and
    `letter_rank` still take an explicit ordering key each; the two may
    differ (see the field doc above) so both stay explicit. `slug` is the
    letter-independent stable identity (#329 P2 / W2) -- required, like the
    original `_spec`.
    """
    group = _group_for(name)
    return name, SheetSpec(v5_code, group, section_rank, group, letter_rank,
                            display, module_key, slug)


def _hidden(name, v5_code=None, module_key=None, *, slug):
    """A sheet that is created and dispatched but deliberately absent from
    the visible nav (merged into another sheet, or not yet restored)."""
    return name, SheetSpec(v5_code, None, None, None, None, None, module_key, slug)


SHEET_REGISTRY = dict([
    _visible('1. Executive Summary', '1', 0, 0, 'Executive Summary', slug='executive_summary'),
    _visible('Plan Data', None, 0, 0, 'Plan Data', slug='plan_data'),
    _visible('2. Assumptions', '4', 1, 1, 'Assumptions', slug='assumptions'),
    _visible('3. Balance Sheet', '1', 3, 3, 'Balance Sheet', slug='balance_sheet'),
    _visible('4. Asset Allocation', '2', 1, 1, 'Asset Allocation', slug='asset_allocation'),
    _visible('5. Net Worth Projection', '1', 1, 1, 'Net Worth', slug='net_worth'),
    _visible('6. Cash Flow Projection', '1', 2, 2, 'Cash Flow', slug='cash_flow'),
    _visible('7. Lifetime Tax', '1', 5, 5, 'Lifetime Taxes', 'lifetime_tax_projection', slug='lifetime_taxes'),
    _visible('8. Charts Dashboard', '1', 4, 4, 'Charts', 'charts_dashboard', slug='charts'),
    # #329 §1.2/§3.3 (W9): restored from hidden -- built and gated
    # identically before and after, only the lettered nav visibility changes.
    # letter_rank 2 sits it between Asset Allocation (1) and Social Security
    # (3), matching #329 §3.3's UI ordering (Roth · HSA · Asset Allocation ·
    # Withdrawal Sequencing · Social Security · ...).
    _visible('9. Retirement Strategy', '1', 2, 2, 'Withdrawal Sequencing', 'retirement_strategy', slug='retirement_strategy'),
    _visible('S-Corp vs LLC', None, 0, 1, 'S-Corp vs LLC', 'scorp_vs_llc', slug='s_corp_vs_llc'),
    _visible('10. Social Security', '2', 3, 3, 'Social Security', 'social_security_timing', slug='social_security'),
    _visible('11. Roth Conversion', '2', 0, 0, 'Roth Conversion', 'roth_conversion_plan', slug='roth_conversion'),
    # section_rank/letter_rank are sort keys, not slots -- 0.5 sits it right
    # after Roth Conversion (rank 0) without renumbering anything else.
    #
    # W8b set `module_key`. The sheet still self-gates its *content* on
    # `hsa_withdrawal_mode == 'optimize'` (it renders a "not applicable" note
    # in every other mode); that is a planning lever, not a feature switch,
    # and both now apply. The toggle decides whether the sheet exists at all;
    # the mode decides what it says when it does. See the `hsa_drawdown`
    # CATALOG entry for why the toggle stops at the sheet and deliberately
    # does not reach the engine's `optimize` branch.
    _visible('11C. HSA Drawdown', '2', 0.5, 0.5, 'HSA Drawdown', 'hsa_drawdown', slug='hsa_drawdown'),
    _visible('12. Charitable Giving', '2', 5, 5, 'Charitable Giving', 'charitable_giving', slug='charitable_giving'),
    # section_rank AND letter_rank 18/19 (above the highest plan-optimizer
    # rank, 17/15 on Housing Comparison, in BOTH dimensions) puts Tax-Loss
    # Harvesting and Gain Harvesting last and adjacent within '2. Optimizers'
    # -- densely, in both physical tab order (section_rank drives
    # WORKBOOK_SECTION_LAYOUT's sheet order, hence the divider tab's listed
    # rows and the real tab strip) and lettering (letter_rank). Moving only
    # one of the two ranks leaves them agreeing on the letter but not the
    # physical position, or vice versa -- W3's "This year's actions" divider
    # (build_workbook_section_divider) renders right before whichever of the
    # two survives module gating and appears first in that physical order.
    _visible('12B. Tax-Loss Harvesting', '2', 18, 18, 'Tax-Loss Harvesting', 'tax_loss_harvesting', slug='tax_loss_harvesting'),
    _visible('12C. Gain Harvesting', '2', 19, 19, 'Gain Harvesting', 'gain_harvesting', slug='gain_harvesting'),
    _visible('13. State Residency', '2', 0, 0, 'State Residency', 'state_residency', slug='state_residency'),
    _visible('14. Estate Plan', '2', 6, 6, 'Estate & Legacy Planning', 'estate_legacy_plan', slug='estate_legacy_planning'),
    _visible('15. Market-Luck Stress Test', '3', 0, 0, 'Monte Carlo', 'market_luck_stress_test', slug='monte_carlo'),
    # #329 §1.2/§3.3 (W9): restored from hidden. rank 2 lands it as '3C'
    # (State Residency=A, S-Corp vs LLC=B) -- matching the catalog entry's
    # own `tab="3C. Scenario Analysis"`, set in anticipation of this.
    _visible('16. Scenario Analysis', '3', 2, 2, 'Scenario Analysis', 'what_if_analysis', slug='scenario_analysis'),
    # W3 (#329 O10): LTC Stress Test is no longer merged into Life Insurance
    # -- it gets its own tab under '4. Risks' (4.1 stress tests), letter_rank
    # 2 so it sits between Survivor (1) and the protection decisions (3+).
    # Same slug W2 assigned it while it was still hidden -- its identity
    # didn't change, only its visibility.
    _visible('17. LTC Stress Test', '3', 2, 2, 'LTC Stress Test', 'long_term_care_stress', slug='ltc_stress_test'),
    _visible('18. Survivor Stress Test', '3', 1, 1, 'Survivor', 'survivor_stress_test', slug='survivor_stress_test'),
    # #329 §1.2/§3.3 (W9): new sheet, rank 2.5 -- the fourth "4.1 stress
    # test", after LTC Stress Test (2) and before the "4.2 protection
    # decisions" that follow (Life Insurance Need at 3, etc).
    # display avoids "/" -- illegal in an openpyxl/Excel worksheet title,
    # unlike the catalog's own "Divorce / QDRO" module name, which only ever
    # appears in cell text, never as a sheet title.
    _visible('39. Divorce QDRO Stress Test', '3', 2.5, 2.5, 'Divorce-QDRO', 'divorce_qdro', slug='divorce_qdro_stress_test'),
    # letter_rank 3 (was 2): LTC Stress Test's split-out tab now sits at 2.
    # slug renamed from W2's 'ltc_life_insurance' -- that name matched the
    # merged concept (#329 O10 unmerges it here); 'life_insurance_need'
    # matches this sheet's module key and its now-standalone identity.
    _visible('19. Life Insurance', '3', 3, 3, 'Life Insurance Need', 'life_insurance_need', slug='life_insurance_need'),
    _visible('20. RMD Audit', '4', 5, 4, 'RMD Audit', 'rmd_audit', slug='rmd_audit'),
    _visible('21. Quality Control', '4', 4, 3, 'Quality Control', slug='quality_control'),
    _visible('22. Glossary', '4', 7, 6, 'Glossary', 'glossary', slug='glossary'),
    _visible('23. Methodology', '4', 6, 5, 'Methodology', 'methodology_rerun', slug='methodology'),
    # #329 §1.2 (W9): restored from hidden. Not in #329 §3.3's UI list (only
    # Asset Allocation is), so this is workbook-only -- no dashboard_step.
    # rank 4 sits after Social Security (3), before Charitable Giving (5).
    _visible('24. Asset Location', '2', 4, 4, 'Asset Location', 'asset_location', slug='asset_location'),
    # W8b: `module_key` set on both YTD sheets. Each names its OWN module key,
    # not the bundle parent's -- the bundle is resolved inside
    # `_base_enabled`, so OPTIONAL_MODULE_SHEETS keeps its one-key-one-sheet
    # shape and the build gate needs no special case. Before W8b both were
    # always-on; per W8a's finding, `optional=True` on the CATALOG entry alone
    # would not have stopped either sheet being built.
    _visible('25. Account Reconciliation', '4', 3, 2, 'Account Reconciliation', 'account_reconciliation', slug='account_reconciliation'),
    _hidden('26. Workbook Warnings', 'H', slug='workbook_warnings'),
    _visible('27. Planning Levers', '4', 7.5, 7.5, 'Planning Levers', slug='planning_levers'),
    _visible('11B. Tax Capacity', '2', 8, 8, 'Tax Capacity', 'tax_capacity', slug='tax_capacity'),
    _visible('29. Spending Summary', '1', 6, 6, 'Spending Summary', 'spending_summary', slug='spending_summary'),
    _visible('30. Education Funding', '2', 9, 9, 'Education Funding', 'education_funding_529', slug='education_funding'),
    # letter_rank 4-6 (was 3-5): the protection decisions now sit after LTC
    # Stress Test's own tab (2) and Life Insurance Need (3) in '4. Risks'.
    _visible('31. Existing Life Insurance', '3', 4, 4, 'Existing Life Insurance', 'existing_life_insurance', slug='existing_life_insurance'),
    _visible('32. Disability Income', '3', 5, 5, 'Disability Income', 'disability_income_insurance', slug='disability_income'),
    _visible('33. P&C Umbrella', '3', 6, 6, 'P&C Umbrella', 'property_casualty_umbrella', slug='pc_umbrella'),
    _visible('34. Business Succession', '2', 12, 12, 'Business Succession', 'business_succession', slug='business_succession'),
    _visible('35. Equity Compensation', '2', 10, 10, 'Equity Compensation', 'equity_compensation', slug='equity_compensation'),
    _visible('36. Special-Needs Planning', '2', 11, 11, 'Special-Needs Planning', 'special_needs_planning', slug='special_needs_planning'),
    _visible('37. Current vs Proposed', '1', 7, 7, 'Current vs. Proposed', 'current_vs_proposed', slug='current_vs_proposed'),
    # 2026-09-09 housing-estimate design, §7.0 H7: the three-axis housing
    # trajectory sweep -- see src/housing_comparison.py.
    # section_rank/letter_rank 17/15 sit right
    # after '11B. Tax Capacity' (16/14), the highest currently used in
    # section '2'/letter_prefix '2', without renumbering anything else.
    # Kept short ("Comparison", not "Trajectory Comparison") because a
    # build-time sheet TITLE is a real openpyxl worksheet name, capped at 31
    # characters -- "38. Housing Trajectory Comparison" (33 chars) tripped
    # that limit.
    _visible('38. Housing Comparison', '2', 17, 15, 'Housing Comparison', 'housing_trajectory_comparison', slug='housing_comparison'),
])

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


def force_override(key) -> Optional[Tuple[str, str]]:
    """``(state, env_var)`` when an env override decides ``key``, else ``None``.

    #330 Q7: the three ``RETIREMENT_SYSTEM_FORCE_*`` variables are already an
    out-of-band admin tier (tests use them). The ticket asked whether the UI
    should grow a writable equivalent; the answer was no -- a second precedence
    rule layered on :func:`_base_enabled`'s existing four is exactly what #329
    exists to stop. What the UI *should* do is **disclose** an active override,
    read-only, so the switch page cannot silently disagree with what the build
    did.

    The precedence here mirrors :func:`_base_enabled` step for step, and must
    keep mirroring it: a disclosure that reports a different winner than the
    gate actually used would be worse than no disclosure at all.
    ``state`` is ``"enabled"`` or ``"disabled"``; ``env_var`` is the variable
    that decided it, so the UI can name it rather than say "something".
    """
    if _force_disabled(key):
        return ("disabled", "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES")
    k = str(key).strip().lower()
    forced_on = os.environ.get('RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES', '')
    if forced_on and k in {m.strip().lower() for m in forced_on.split(',') if m.strip()}:
        return ("enabled", "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES")
    if os.environ.get('RETIREMENT_SYSTEM_FORCE_ALL_MODULES') == '1':
        return ("enabled", "RETIREMENT_SYSTEM_FORCE_ALL_MODULES")
    return None


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
    # #330 §3.3 (W8b): a bundled module's switch is its parent's row. Resolved
    # HERE, below the env tier and above the saved-toggle read, which puts it
    # in exactly one place: every consumer -- the build gate's generic loop
    # over OPTIONAL_MODULE_SHEETS, effective_enabled_modules(), module_status()
    # and module_enabled() itself -- goes through this function, so none of
    # them can forget the bundle the way `deterministic_engine.py` forgot the
    # accessor before W7.
    #
    # Below the env tier on purpose: the RETIREMENT_SYSTEM_FORCE_* variables
    # are a per-key admin tier (the gating tests name individual modules), and
    # a member named there must still win for itself. The parent's own force
    # state is not skipped either -- the recursive call runs it through this
    # same ladder from the top.
    # `k` (lower/stripped) as the fallback lookup mirrors the case-insensitive
    # `opt` scan below: every catalog key is lowercase snake_case, so a caller
    # spelling one differently would otherwise skip the bundle and fall through
    # to the member's own (never-set) toggle, silently reading default-on.
    _parent = getattr(CATALOG.get(key) or CATALOG.get(k), 'gated_by', None)
    if _parent:
        return _base_enabled(c, _parent)
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
    """Per-module gating status for the Plan Features settings UI.

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
      * ``forced`` / ``forced_by`` — #330 Q7's read-only disclosure. Non-None
        when a ``RETIREMENT_SYSTEM_FORCE_*`` env override, not the saved
        toggle, is what decided ``enabled``; ``forced_by`` names the variable.
        See :func:`force_override`.
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
        # #330 Q7. Read-only disclosure, never a new precedence rule: the
        # override already decided `enabled` above, via the same helper the
        # build uses. This only says so out loud.
        forced = force_override(key)
        status[key] = {
            "enabled": module_enabled(c, key),
            "auto_enabled": bool(auto),
            "required_by": required_by_map.get(key, []),
            "forced": forced[0] if forced else None,
            "forced_by": forced[1] if forced else None,
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
    ids, unique legacy sheet names, comparison-mode only on Optimization, and
    (#330 §3.4) well-formed soft dependencies / engine-participation flags.
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
        # (4b) #330 §3.4. A soft dependency must name a real module, must not
        # name itself, and must not duplicate a hard prerequisite: anything in
        # `requires_outputs` is auto-enabled by effective_enabled_modules(), so
        # it can never be observed off, and a "shows less without it" note for
        # it would be unreachable text. Declaring both is a modelling error,
        # not a belt-and-braces.
        for dep, loses in m.degrades_without:
            assert dep in CATALOG, f"{key}: degrades_without unknown module {dep!r}"
            assert dep != key, f"{key}: degrades_without itself"
            # The phrase is half the field's value -- it is what makes the
            # reverse warning say something instead of just naming modules.
            assert loses and loses.strip(), (
                f"{key}: degrades_without {dep!r} with no description of what "
                f"is lost; the warning on {dep}'s switch has nothing to say.")
            assert dep not in m.requires_outputs, (
                f"{key}: {dep!r} is declared as both a hard prerequisite and a "
                f"soft dependency. requires_outputs auto-enables it, so it can "
                f"never be off -- pick one.")
            # A core module has no toggle, so it is never off and nothing can
            # degrade without it.
            assert CATALOG[dep].optional, (
                f"{key}: degrades_without {dep!r}, which is a core always-on "
                f"module -- there is no switch for the warning to attach to.")
        # (4d) #330 §5.3 (W6). A gate declaration must be complete and must
        # match its kind: a plan flag names the row that switches it and how
        # that row reads on screen; a module toggle names nothing, because the
        # key is the toggle. A half-declared gate is worse than none -- the
        # frontend would look the step up, find an entry, and evaluate an
        # undefined reference.
        assert m.gate_kind in GATE_KINDS, (
            f"{key}: bad gate_kind {m.gate_kind!r}; expected one of {GATE_KINDS}")
        if m.gate_kind == GATE_PLAN_FLAG:
            assert not m.optional, (
                f"{key}: gate_kind={GATE_PLAN_FLAG!r} with optional=True. The two "
                f"mechanisms are alternatives, not layers -- a feature gated by "
                f"both is the DAF double-gate #330 Q2 exists to end.")
            assert m.gate_ref and len(m.gate_ref) == 3 and all(m.gate_ref), (
                f"{key}: gate_kind={GATE_PLAN_FLAG!r} needs a complete "
                f"(section, subsection, label) gate_ref; got {m.gate_ref!r}")
            assert m.gate_enable_label, (
                f"{key}: gate_kind={GATE_PLAN_FLAG!r} needs gate_enable_label -- "
                f"the flag row's display name, which its CSV label "
                f"({m.gate_ref[2]!r}) does not give. Without it the enable-note "
                f"has no click-path to name.")
            assert not m.sheet, (
                f"{key}: a plan flag owns no workbook sheet, but names "
                f"{m.sheet!r}; the catalog-to-registry join expects a module "
                f"behind every sheet and a toggle behind every module.")
        else:
            assert m.gate_ref is None and m.gate_enable_label is None, (
                f"{key}: gate_ref/gate_enable_label are plan-flag fields, but "
                f"gate_kind is {m.gate_kind!r}; the module key is the toggle.")
        # (4e) #330 §3.3 (W8b). A bundle must be well-formed before anything
        # resolves through it: `_base_enabled` follows `gated_by` exactly one
        # hop and treats the answer as final, so a dangling, self-referential
        # or chained parent would silently mis-gate rather than fail.
        if m.gated_by is not None:
            assert m.gated_by != key, f"{key}: gated_by itself"
            assert m.gated_by in CATALOG, (
                f"{key}: gated_by {m.gated_by!r}, which is not a catalogued "
                f"module -- _base_enabled would resolve it to the default-on "
                f"branch and the bundle would read as permanently ON.")
            parent = CATALOG[m.gated_by]
            assert m.optional, (
                f"{key}: gated_by {m.gated_by!r} but optional=False. A bundled "
                f"module IS switched -- by its parent's row -- so calling it "
                f"core would put it in core_keys(), which means always-on.")
            assert parent.optional, (
                f"{key}: gated_by {m.gated_by!r}, which is not optional. The "
                f"parent's toggle is this module's switch; a core parent has "
                f"no toggle to be one.")
            assert parent.gate_kind == GATE_MODULE_TOGGLE, (
                f"{key}: gated_by {m.gated_by!r}, whose gate_kind is "
                f"{parent.gate_kind!r}. A bundle parent's switch must be a "
                f"client_optional_functions.csv row, because that is what the "
                f"member inherits.")
            assert parent.gated_by is None, (
                f"{key}: gated_by {m.gated_by!r}, which is itself gated_by "
                f"{parent.gated_by!r}. Bundles are one level deep -- "
                f"_base_enabled resolves a single hop, so a chain would stop "
                f"at the middle module's own (never-set) toggle.")
        # (4c) engine_participation describes what a *toggle* does to the
        # projection. A core module has no toggle.
        if m.engine_participation:
            assert m.optional, (
                f"{key}: engine_participation=True on a core always-on module; "
                f"the flag describes a toggle's effect on the projection and "
                f"there is no toggle here.")

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

    # #329 P2 (W2): slugs are the letter-independent stable identity every
    # cross-reference resolves through (FINAL_SHEET_RENAMES[slug]); a blank or
    # colliding slug would silently make that lookup ambiguous or fail.
    _slugs: Dict[str, str] = {}
    for _name, _spec_ in SHEET_REGISTRY.items():
        assert _spec_.slug, f"sheet {_name!r} has no slug"
        assert _spec_.slug not in _slugs, (
            f"duplicate slug {_spec_.slug!r} on {_name!r} and {_slugs[_spec_.slug]!r}")
        _slugs[_spec_.slug] = _name

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
            # W6 widened this from `optional` to "has a gate of some kind": a
            # plan flag gates a step exactly as a toggle does, it just reads
            # the switch from plan data. What is still an error is gating a
            # step from a module that has no switch at all.
            assert m.optional or m.gate_kind == GATE_PLAN_FLAG, (
                f"{key}: dashboard_step/csv_sections require a switch -- either "
                f"optional=True or gate_kind={GATE_PLAN_FLAG!r}")
        if m.dashboard_step:
            # Uniqueness spans BOTH gate maps: step_gate_map() and
            # flag_gate_map() are read by one frontend lookup chain, so a step
            # claimed twice would resolve to whichever map is consulted first.
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

