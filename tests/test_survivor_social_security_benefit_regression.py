"""Finding FIN-001 (system review 2026-09-25, Wave 1 item WI-103):
the Social Security survivor benefit used to be a one-time snapshot taken at
the death year -- zero if the worker died before their planned claim year,
frozen at its death-year nominal dollar amount forever after (no COLA), and
payable at any survivor age with no age-60 gate or early-survivor-claim
reduction.

This pins the fix in src/projection_stages/income.py: the survivor benefit is
rebuilt each year from the deceased's own record (the widow(er) limit if they
had claimed, PIA plus delayed retirement credits earned to death if they had
not), indexed by COLA through the CURRENT year, gated on the survivor being
at least 60, and reduced for an early survivor claim.

These plans are built entirely in code and read nothing from ``input/``,
following the same pattern as
tests/test_spousal_ss_excess_benefit_regression.py.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project


def _build(members, income, ss_cola=0.0):
    plan = {
        "plan_start": 2026,
        "filing_status": "MFJ",
        "survivor_filing_status": "Single",
        "state": "Illinois",
        "members": members,
        "accounts": [
            {"id": "M1_IRA", "acct_type": "traditional_ira", "owner_idx": 0,
             "balance": 800_000.0, "label": "A IRA"},
            {"id": "M2_IRA", "acct_type": "traditional_ira", "owner_idx": 1,
             "balance": 800_000.0, "label": "B IRA"},
            {"id": "Checking", "acct_type": "checking", "owner_idx": 0,
             "balance": 200_000.0, "label": "Checking"},
        ],
        "assumptions": {"return_rate": 0.05, "inflation": 0.0, "ss_cola": ss_cola,
                        "bracket_inflation": 0.0, "irmaa_inflation": 0.0,
                        "roth_policy": "none", "rmd_start_age": 75,
                        "hsa_contribution": 0.0},
        "income": income,
        "spending": {"annual_base": 40_000.0, "wellness_annual": 0.0},
        "home_value": 0.0, "mortgage_balance": 0.0, "auto_value": 0.0,
    }
    c = build_plan_from_json(plan, "")
    c = ensure_engine_config(c, source="test_fin001")
    c["roth_policy"] = "none"
    c["roth_optimized_policy"] = "none"
    c["ss_funding_discount_pct"] = 0.0
    return c


def _ss_by_year(c):
    return {r["year"]: (round(r["h_ss"], 2), round(r["w_ss"], 2)) for r in project(c)}


_MEMBERS = [
    {"name": "Alex", "nickname": "Alex", "dob_year": 1960, "dob_month": 1,
     "retirement_year": 2026, "mortality_age": 95},
    {"name": "Blair", "nickname": "Blair", "dob_year": 1958, "dob_month": 1,
     "retirement_year": 2026, "mortality_age": 95},
]


class SurvivorBenefitPreClaimDeathTests(unittest.TestCase):
    def test_survivor_gets_a_nonzero_pia_based_benefit_when_worker_dies_before_claiming(self):
        """Alex (PIA 3,000, planned to claim at 70) dies at 66, before ever
        claiming. Blair (born 1958, already 68 in 2026, well past her own
        FRA) is the survivor. The old code paid Blair $0 forever on Alex's
        record (h_death_yr < h_ss_yr). The fix values Alex's record at his
        full, un-reduced PIA (he died before FRA 67, so no DRC applies) and
        pays it to Blair -- who, already past her own FRA, gets it
        unreduced.
        """
        income = {"earned_income": 0.0, "h_ss_pia": 3_000.0, "w_ss_pia": 0.0,
                  "h_ss_claim_age": 70, "w_ss_claim_age": 70}
        c = _build(_MEMBERS, income)
        c["h_death_yr"] = 1960 + 66  # Alex dies the year he turns 66
        ss = _ss_by_year(c)
        death_yr = 1960 + 66
        self.assertGreater(ss[death_yr + 1][1], 0.0,
                            msg="survivor benefit must be nonzero when the worker died before claiming")
        self.assertAlmostEqual(ss[death_yr + 1][1], 3_000.0 * 12, places=2,
                                msg="pre-FRA death: survivor benefit = full PIA (no DRC, no reduction -- survivor past her own FRA)")
        self.assertEqual(ss[death_yr + 1][0], 0.0, msg="the deceased pays nothing on his own record")


class SurvivorBenefitColaContinuationTests(unittest.TestCase):
    def test_survivor_benefit_keeps_growing_with_cola_after_the_death_year(self):
        """Alex (PIA 3,000) claims at his own FRA (67, so his claimed amount
        equals his PIA) and dies at 80, well after claiming. With a 3% COLA,
        the old code froze the survivor benefit at its death-year dollar
        amount forever; the fix must keep compounding it every year after,
        exactly like a living benefit does.
        """
        income = {"earned_income": 0.0, "h_ss_pia": 3_000.0, "w_ss_pia": 0.0,
                  "h_ss_claim_age": 67, "w_ss_claim_age": 70}
        c = _build(_MEMBERS, income, ss_cola=0.03)
        h_death_yr = 1960 + 80
        c["h_death_yr"] = h_death_yr
        ss = _ss_by_year(c)
        w_ss_plus_1 = ss[h_death_yr + 1][1]
        w_ss_plus_4 = ss[h_death_yr + 4][1]
        self.assertGreater(w_ss_plus_1, 0.0)
        self.assertGreater(
            w_ss_plus_4, w_ss_plus_1 * 1.02,
            msg="survivor benefit must keep compounding by COLA in the years after death, not stay frozen",
        )
        self.assertAlmostEqual(w_ss_plus_4 / w_ss_plus_1, 1.03 ** 3, places=2,
                                msg="the growth between two post-death years must match the COLA rate exactly")


class SurvivorBenefitAge60GateTests(unittest.TestCase):
    def test_no_survivor_benefit_before_the_survivor_turns_60(self):
        """Blair (born 1990) is only 36 when Alex (PIA 3,000, claims at 67)
        dies in 2026 -- far short of the age-60 survivor floor. The old code
        had no age gate at all and would have paid a full survivor benefit
        immediately; the fix must pay nothing until Blair turns 60 (in 2050).
        """
        members = [
            {"name": "Alex", "nickname": "Alex", "dob_year": 1959, "dob_month": 1,
             "retirement_year": 2026, "mortality_age": 67},
            {"name": "Blair", "nickname": "Blair", "dob_year": 1990, "dob_month": 1,
             "retirement_year": 2026, "mortality_age": 95},
        ]
        income = {"earned_income": 0.0, "h_ss_pia": 3_000.0, "w_ss_pia": 0.0,
                  "h_ss_claim_age": 67, "w_ss_claim_age": 70}
        c = _build(members, income)
        c["h_death_yr"] = 2026
        ss = _ss_by_year(c)
        self.assertEqual(ss[2030][1], 0.0, msg="Blair is 40 in 2030 -- no survivor benefit before 60")
        self.assertEqual(ss[2049][1], 0.0, msg="Blair is 59 in 2049 -- still not yet 60")
        self.assertGreater(ss[2050][1], 0.0, msg="Blair turns 60 in 2050 -- survivor benefit must start")


if __name__ == "__main__":
    unittest.main()
