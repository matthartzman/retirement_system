"""Finding FIN-003 (system review 2026-09-25, Wave 1 item WI-104):
the over-65 standard-deduction add-on count (n65) and the OBBBA senior bonus
were built from raw birth-year age arithmetic with no alive check, so a
survivor year double-counted the deceased spouse's own age-65 add-on and
senior bonus on top of the survivor's -- a Single filer's std_ded reflected
two people's over-65 counts.

This pins the fix in src/projection_stages/roth_conversion_and_agi_tax.py
(apply_agi_and_tax) and src/planning_engines.py (plan_roth_conversion): n65
is now (h_alive and h_age>=65) + (w_alive and w_age>=65). It also pins that
OBBBA's senior bonus (src/core.py senior_bonus_deduction) is denied to MFS
filers.

Built entirely in code, following the pattern of
tests/test_spousal_ss_excess_benefit_regression.py.
"""
from __future__ import annotations

import unittest

from src.core import senior_bonus_deduction, standard_deduction
from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project


def _build(members, income, h_death_yr=None):
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
        "assumptions": {"return_rate": 0.05, "inflation": 0.0, "ss_cola": 0.0,
                        "bracket_inflation": 0.0, "irmaa_inflation": 0.0,
                        "roth_policy": "none", "rmd_start_age": 75,
                        "hsa_contribution": 0.0},
        "income": income,
        "spending": {"annual_base": 40_000.0, "wellness_annual": 0.0},
        "home_value": 0.0, "mortgage_balance": 0.0, "auto_value": 0.0,
    }
    c = build_plan_from_json(plan, "")
    c = ensure_engine_config(c, source="test_fin003")
    c["roth_policy"] = "none"
    c["roth_optimized_policy"] = "none"
    c["ss_funding_discount_pct"] = 0.0
    if h_death_yr is not None:
        c["h_death_yr"] = h_death_yr
    return c


class SurvivorStandardDeductionAliveGatingTests(unittest.TestCase):
    def test_survivor_year_counts_only_the_survivors_own_over_65_add_on(self):
        """Alex (born 1946, so already 80 in 2026) dies at 80. Blair (born
        1950, 76 in 2026 -- also over 65) is the survivor, filing Single
        starting the year after death. The old code counted BOTH spouses'
        age-65 add-ons and senior bonuses (n65 built from raw age with no
        alive check) even though Alex is dead; the fix must count only
        Blair's.
        """
        members = [
            {"name": "Alex", "nickname": "Alex", "dob_year": 1946, "dob_month": 1,
             "retirement_year": 2020, "mortality_age": 80},
            {"name": "Blair", "nickname": "Blair", "dob_year": 1950, "dob_month": 1,
             "retirement_year": 2020, "mortality_age": 95},
        ]
        income = {"earned_income": 0.0, "h_ss_pia": 0.0, "w_ss_pia": 0.0,
                  "h_ss_claim_age": 70, "w_ss_claim_age": 70}
        h_death_yr = 2026  # Alex dies the year he turns 80
        c = _build(members, income, h_death_yr=h_death_yr)
        rows = {r["year"]: r for r in project(c)}

        death_plus_2 = h_death_yr + 2
        row = rows[death_plus_2]
        single_base = standard_deduction(death_plus_2, "Single", 0.0, n_over_65=0)
        one_add_on = standard_deduction(death_plus_2, "Single", 0.0, n_over_65=1) - single_base
        expected_senior_bonus = senior_bonus_deduction(
            death_plus_2, "Single", row.get("agi", 0.0), n_over_65=1
        )
        expected_std_ded = single_base + one_add_on + expected_senior_bonus

        self.assertAlmostEqual(
            row["std_ded"], expected_std_ded, delta=1.0,
            msg="survivor year std_ded must reflect exactly ONE over-65 add-on/senior bonus, not two",
        )


class SeniorBonusMfsExclusionTests(unittest.TestCase):
    def test_senior_bonus_is_denied_to_mfs_filers(self):
        # OBBBA Sec. 70103 requires a joint return for a married taxpayer to
        # claim the senior deduction; MFS gets none regardless of age.
        self.assertEqual(senior_bonus_deduction(2026, "MFS", 0.0, n_over_65=2), 0.0)
        self.assertGreater(senior_bonus_deduction(2026, "MFJ", 0.0, n_over_65=2), 0.0)
        self.assertGreater(senior_bonus_deduction(2026, "Single", 0.0, n_over_65=1), 0.0)


if __name__ == "__main__":
    unittest.main()
