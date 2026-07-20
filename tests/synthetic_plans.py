"""Genuinely synthetic plan library for the golden-master engine gate.

WHY THIS EXISTS
---------------
The original golden-master library (tests/fixtures/golden_master_engine_cases.json,
driven by tests/test_phase5_validation_maturity.py) loaded the *live client plan*
from ``input/client_data.csv`` and applied five mutators to it. Because
``data_io.load_csv`` merges every sibling ``input/client_*.csv`` — household,
policy, optional-functions — an edit to any of the advisor's real plan data moved
the pinned dollar totals. The gate therefore could not distinguish "the engine
broke" from "the client changed their retirement date", and its
``delta=50000.0`` tolerance existed mainly to absorb that coupling.

Every plan in this module is written from scratch in code. Nothing here reads
``input/`` — see ``test_synthetic_golden_master.py`` for the tests that assert
that property mechanically (source-text scan + a run against a workspace with no
client files at all).

WHY THE FLAT-JSON BUILDER
-------------------------
``data_io.parse_client`` (the CSV path) resolves ``client_holdings.csv`` against
the *repo root*, not the redirectable workspace root::

    candidate_input_files('client_holdings.csv', ..., root=Path(_project_root))

so it reads the advisor's real holdings no matter how the environment is set up.
``data_io.build_plan_from_json``'s flat-wizard branch has no disk reads at all,
takes accounts inline, and — critically — honors an explicit ``plan_start``
instead of ``datetime.date.today().year``. That makes these baselines stable
across calendar years, which the CSV-derived ones never were.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, Mapping

from src.core import TaxLot
from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import optimize_roth_conversion_strategy
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES

# Pinned so the whole library is calendar-stable: the projection horizon, the
# tax-bracket inflation exponents, and the RMD ages are all measured from here.
# Without this the engine would default to datetime.date.today().year and every
# pinned dollar amount would silently drift on January 1.
PLAN_START = 2026

# Frozen holdings price used to build synthetic tax lots (see _tlh_lots). This is
# the same snapshot tests/golden_pricing.py pins the provider to, so an
# underwater lot stays underwater by exactly the amount intended.
_VTI = FROZEN_GOLDEN_MASTER_PRICES["VTI"]


def _accounts() -> list[dict[str, Any]]:
    """The standard synthetic account set: pre-tax heavy, with Roth/taxable/HSA/cash.

    Deliberately pre-tax heavy so Roth-conversion policy and RMDs both bite —
    a balanced-by-tax-bucket household would make the Roth scenarios inert.

    Member 1 holds BOTH a 401(k) and a traditional IRA on purpose. The engine
    rolls the owner-0 workplace plan into an owner-0 traditional IRA at
    ``rollover_401k_yr``; if that member has no IRA the rollover destination
    falls back to the 401(k) itself and the balance is zeroed. Modelling a
    realistic 401(k)+IRA pair keeps the rollover a true transfer.
    """
    return [
        {"id": "Member_1_401k", "acct_type": "401k", "owner_idx": 0,
         "balance": 700_000.0, "label": "Alex's 401(k)"},
        {"id": "Member_1_IRA", "acct_type": "traditional_ira", "owner_idx": 0,
         "balance": 700_000.0, "label": "Alex's Traditional IRA"},
        {"id": "Member_2_IRA", "acct_type": "traditional_ira", "owner_idx": 1,
         "balance": 750_000.0, "label": "Blair's Traditional IRA"},
        {"id": "Member_1_Roth", "acct_type": "roth_ira", "owner_idx": 0,
         "balance": 210_000.0, "label": "Alex's Roth IRA"},
        {"id": "Joint_Trust", "acct_type": "trust", "owner_idx": 0,
         "balance": 900_000.0, "label": "Joint Revocable Trust"},
        {"id": "Member_1_HSA", "acct_type": "hsa", "owner_idx": 0,
         "balance": 95_000.0, "label": "Alex's HSA"},
        {"id": "Family_Checking", "acct_type": "checking", "owner_idx": 0,
         "balance": 120_000.0, "label": "Family Checking"},
    ]


def base_plan() -> Dict[str, Any]:
    """A married-filing-jointly couple, both retiring early in the horizon.

    Values are round numbers chosen to be readable, not to resemble any real
    client. Ages are picked so that the first RMD, the first Social Security
    claim, and the Medicare/IRMAA switch all land inside the projection window.
    """
    return {
        "plan_start": PLAN_START,
        "filing_status": "MFJ",
        "survivor_filing_status": "Single",
        "state": "Illinois",
        "members": [
            {"name": "Alex Synthetic", "nickname": "Alex", "dob_year": 1964,
             "dob_month": 6, "retirement_year": 2027, "mortality_age": 90},
            {"name": "Blair Synthetic", "nickname": "Blair", "dob_year": 1966,
             "dob_month": 3, "retirement_year": 2028, "mortality_age": 92},
        ],
        "accounts": _accounts(),
        "assumptions": {
            "return_rate": 0.06,
            "inflation": 0.025,
            "bracket_inflation": 0.02,
            "irmaa_inflation": 0.02,
            "ss_cola": 0.02,
            "mc_volatility": 0.12,
            "roth_policy": "fill_to_bracket",
            "roth_target_rate": 0.22,
            "rmd_start_age": 75,
            "hsa_contribution": 0.0,
        },
        "income": {
            "earned_income": 180_000.0,
            "income_growth": 0.03,
            "h_ss_pia": 3_400.0,
            "w_ss_pia": 2_600.0,
            "ss_claim_age": 70,
        },
        "spending": {
            # Sized so the plan stays solvent to the terminal year: an
            # exhausted portfolio flattens every dollar metric to zero and the
            # gate stops being able to see engine changes at all.
            "annual_base": 110_000.0,
            "wellness_annual": 14_000.0,
            "wellness_inflation": 0.05,
        },
        # No home, no mortgage, no autos, no note receivable, no annuities:
        # every one of those is an independently-tested subsystem and leaving
        # them at zero keeps these baselines readable and their movements
        # attributable.
        "home_value": 0.0,
        "mortgage_balance": 0.0,
        "auto_value": 0.0,
    }


def _single_filer_plan() -> Dict[str, Any]:
    """Same engine, one member — exercises the Single bracket/deduction path."""
    plan = base_plan()
    plan["members"] = [plan["members"][0]]
    plan["filing_status"] = "Single"
    plan["accounts"] = [a for a in _accounts() if a["id"] != "Member_2_IRA"]
    plan["income"] = {
        "earned_income": 140_000.0,
        "income_growth": 0.03,
        "h_ss_pia": 3_400.0,
        "ss_claim_age": 70,
    }
    plan["spending"] = {"annual_base": 80_000.0, "wellness_annual": 9_000.0,
                        "wellness_inflation": 0.05}
    return plan


# ─────────────────────────────────────────────────────────────────────────────
# Post-build overrides
#
# A few engine subsystems (DAF, per-account dividend reinvestment, TLH) are not
# reachable through the flat-wizard JSON schema — build_plan_from_json hardcodes
# them off. They are set directly on the engine config, before Roth optimization
# runs, so the optimizer sees the same world the projection will.
# ─────────────────────────────────────────────────────────────────────────────

def _enable_daf(c: Dict[str, Any]) -> None:
    """Fund a donor-advised fund in year 3, then grant it out over 10 years."""
    c["daf_enabled"] = True
    c["daf_year"] = PLAN_START + 2
    c["daf_amount"] = 250_000.0
    c["daf_use_start"] = PLAN_START + 3
    c["daf_use_end"] = PLAN_START + 12
    c["daf_use_amount"] = 25_000.0


def _disable_dividend_reinvestment(c: Dict[str, Any]) -> None:
    """Take taxable-account distributions in cash instead of reinvesting them.

    Exercises planning_engines' dividend-cash sub-balance path: the distribution
    stops compounding at the account return and earns cash_yield_rate instead,
    while still being taxed as it is thrown off.
    """
    c["portfolio_income_reduces_growth"] = True
    c["cash_yield_rate"] = 0.02
    assumptions = dict(c.get("account_taxable_income_assumptions") or {})
    for acct_id in ("Joint_Trust",):
        info = dict(assumptions.get(acct_id) or {})
        info.update({
            "total_distribution_yield": 0.020,
            "qualified_dividend_fraction": 0.85,
            "reinvest_dividends": False,
        })
        assumptions[acct_id] = info
    c["account_taxable_income_assumptions"] = assumptions


def _enable_tlh(c: Dict[str, Any]) -> None:
    """Turn on tax-loss harvesting against deliberately underwater synthetic lots.

    build_plan_from_json produces an empty lot book, so TLH would be a no-op
    without lots to harvest. Two VTI lots are seeded in the taxable trust at a
    cost basis well above the frozen price, so each has a realizable loss that
    clears the min-loss floors. Prices come from the same frozen snapshot the
    test pins the provider to, so the loss size is exact.
    """
    c["tlh_policy"] = "apply"
    c["tlh_transaction_cost_bps"] = 5.0
    c["tlh_min_loss_dollars"] = 500.0
    c["tlh_min_loss_pct"] = 0.05
    c["tlh_annual_ceiling"] = 0.0
    lots = {
        "Joint_Trust": {
            "VTI": [
                # 1,000 sh bought at 1.35x the frozen price → ~$130k unrealized loss.
                TaxLot(qty=1_000.0, cost_basis=1_000.0 * _VTI * 1.35,
                       purchase_date=f"{PLAN_START - 3}-02-15", symbol="VTI"),
                # 400 sh bought at 1.20x → ~$30k unrealized loss.
                TaxLot(qty=400.0, cost_basis=400.0 * _VTI * 1.20,
                       purchase_date=f"{PLAN_START - 1}-09-01", symbol="VTI"),
            ]
        }
    }
    c["lots_by_account"] = lots
    engine = c.get("lot_engine")
    if engine is not None:
        engine.lots = lots
        engine.prices = dict(FROZEN_GOLDEN_MASTER_PRICES)


def _no_voluntary_roth(c: Dict[str, Any]) -> None:
    c["roth_policy"] = "none"
    c["roth_optimized_policy"] = "none"
    c["roth_optimization"] = {}


def _high_spending(c: Dict[str, Any]) -> None:
    c["spend_base"] = float(c["spend_base"]) * 1.20


def _lower_returns(c: Dict[str, Any]) -> None:
    c["ret"] = 0.04
    c["ret_stock"] = 0.055
    c["ret_bond"] = 0.03


def _early_survivor(c: Dict[str, Any]) -> None:
    """Kill member 1 five years in: filing flips to Single, survivor SS applies."""
    death_yr = int(c["plan_start"]) + 5
    c["h_death_yr"] = death_yr
    c["first_death_yr"] = death_yr
    for member in c.get("members", []):
        if member.get("role") == "member_1":
            member["death_yr"] = death_yr


# ─────────────────────────────────────────────────────────────────────────────
# Scenario registry
# ─────────────────────────────────────────────────────────────────────────────

class Scenario:
    def __init__(self, name: str, doc: str,
                 plan: Callable[[], Dict[str, Any]] = base_plan,
                 override: Callable[[Dict[str, Any]], None] | None = None,
                 optimize_roth: bool = True):
        self.name = name
        self.doc = doc
        self._plan = plan
        self._override = override
        self.optimize_roth = optimize_roth

    def plan(self) -> Dict[str, Any]:
        return copy.deepcopy(self._plan())

    def build(self) -> Dict[str, Any]:
        """Assemble the engine config, mirroring prepare_config_from_json.

        The only difference from ``report_compute.prepare_config_from_json`` is
        that the scenario override lands between the first normalization and the
        Roth optimizer, so the optimizer scores the same world the projection
        will actually run.
        """
        c = build_plan_from_json(self.plan(), "")
        c = ensure_engine_config(c, source="synthetic")
        if self._override is not None:
            self._override(c)
        if self.optimize_roth:
            c = optimize_roth_conversion_strategy(c)
            c = ensure_engine_config(c, source="synthetic.optimized")
        return c


SCENARIOS: Dict[str, Scenario] = {s.name: s for s in [
    Scenario(
        "baseline_balanced_couple",
        "MFJ couple, 6% nominal return, bracket-filling Roth policy. The control "
        "case: every other scenario is this one with a single dimension moved, so "
        "a diff against this baseline localizes what an engine change touched.",
    ),
    Scenario(
        "no_voluntary_roth_policy",
        "Same household with all voluntary Roth conversion switched off. Isolates "
        "the RMD/pre-tax-drawdown path and the lifetime-tax consequence of leaving "
        "pre-tax balances untouched — pins the no-conversion branch of the engine.",
        override=_no_voluntary_roth,
    ),
    Scenario(
        "high_spending_pressure",
        "Core spending raised 20% against an unchanged portfolio. Exercises the "
        "withdrawal-ordering cascade under sustained drawdown and the interaction "
        "between larger withdrawals and the Roth conversion headroom.",
        override=_high_spending,
    ),
    Scenario(
        "lower_return_environment",
        "Portfolio return cut to 4% (equity 5.5% / bond 3%). Pins the compounding "
        "path and confirms that terminal net worth and lifetime tax both respond "
        "to the return assumption rather than being dominated by fixed cashflows.",
        override=_lower_returns,
    ),
    Scenario(
        "early_survivor_compression",
        "Member 1 dies in year 6. Exercises the survivor transition: MFJ→Single "
        "brackets and standard deduction, survivor Social Security, and the "
        "inherited-account/RMD consequences of a compressed two-life horizon.",
        override=_early_survivor,
    ),
    Scenario(
        "single_filer",
        "One-member household filing Single from year 1. The five stresses above "
        "are all MFJ, so without this the Single bracket table, standard "
        "deduction, IRMAA thresholds and NIIT threshold are only reachable "
        "through the survivor transition, never from the start of a plan.",
        plan=_single_filer_plan,
    ),
    Scenario(
        "donor_advised_fund",
        "Baseline plus a $250k DAF contribution in year 3 granted out at $25k/yr "
        "for ten years. Pins the DAF lump/grant cashflow and its effect on the "
        "deduction and on the balance available to convert.",
        override=_enable_daf,
    ),
    Scenario(
        "dividends_not_reinvested",
        "Baseline with taxable-trust distributions taken in cash rather than "
        "reinvested. Pins the dividend-cash sub-balance path in planning_engines "
        "— the account's cash drag compounds differently from its holdings, and "
        "that divergence is invisible in every other scenario.",
        override=_disable_dividend_reinvestment,
    ),
    Scenario(
        "tax_loss_harvesting",
        "Baseline plus TLH enabled against seeded underwater VTI lots in the "
        "taxable trust. Pins loss realization, the basis/holding-period reset, "
        "the transaction-cost drag, and the carryforward that offsets later gains.",
        override=_enable_tlh,
    ),
]}


# ─────────────────────────────────────────────────────────────────────────────
# Metric extraction — same metric set the plan-coupled fixture pinned.
# ─────────────────────────────────────────────────────────────────────────────

def project_metrics(c: Mapping[str, Any]) -> Dict[str, Any]:
    from src.planning_engines import project

    rows = project(c)
    terminal = rows[-1]
    first = rows[0]
    first_rmd = next((r for r in rows if float(r.get("rmd_total", 0) or 0) > 0), None)
    first_conv = next((r for r in rows if float(r.get("roth_conv", 0) or 0) > 0), None)
    return {
        "plan_start": int(c["plan_start"]),
        "plan_end": int(c["plan_end"]),
        "row_count": len(rows),
        "terminal_year": int(terminal["year"]),
        "terminal_total_nw": round(float(terminal.get("total_nw", 0) or 0), 2),
        "terminal_liquid_nw": round(
            float(terminal.get("pretax_nw", 0) or 0)
            + float(terminal.get("roth_nw", 0) or 0)
            + float(terminal.get("trust_nw", 0) or 0)
            + float(terminal.get("hsa_nw", 0) or 0), 2),
        "lifetime_tax": round(sum(float(r.get("total_tax", 0) or 0) for r in rows), 2),
        "total_roth_conversion": round(sum(float(r.get("roth_conv", 0) or 0) for r in rows), 2),
        "first_year_total_tax": round(float(first.get("total_tax", 0) or 0), 2),
        "first_rmd_year": int(first_rmd["year"]) if first_rmd else None,
        "first_rmd_total": round(float(first_rmd.get("rmd_total", 0) or 0), 2) if first_rmd else 0,
        "first_conversion_year": int(first_conv["year"]) if first_conv else None,
        "first_conversion_amount": round(float(first_conv.get("roth_conv", 0) or 0), 2) if first_conv else 0,
        "selected_roth_strategy": (c.get("roth_optimization") or {}).get("selected_label", ""),
    }
