"""Excess-spousal Social Security benefit: timing gate and SSA amount.

Item 2.4 (finding P7) corrected two defects in the deterministic engine's
spousal Social Security top-up:

1. TIMING. The top-up was paid regardless of whether the *worker* (the spouse
   whose PIA the spousal amount derives from) had actually filed. Real SSA law:
   a spousal benefit cannot be paid until the worker files for their own
   retirement benefit. The engine now pays the claimant only their own reduced
   benefit until the worker's claim year, then adds the excess-spousal amount.

2. AMOUNT. The old formula was ``max(own_benefit, 0.5 * worker_PIA * factor)``.
   That is wrong twice over: (a) the greater-of form discards the claimant's
   permanent early-claim reduction on their own record, and (b) it applied the
   *own-benefit* reduction schedule to the spousal amount. The correct SSA
   "excess spousal" method is::

       own_reduced_benefit + max(0, 0.5*worker_PIA - own_PIA) * excess_factor

   where ``excess_factor`` follows the spousal reduction schedule (25/36 of 1%
   per month for the first 36 months before FRA, then 5/12 of 1% per month
   beyond, and NO delayed-retirement credits past FRA), keyed to the claimant's
   age when the spousal benefit first becomes payable.

Every expected dollar figure here was derived by hand from that method and
cross-checked against the engine; see the per-case comments.

These plans are built entirely in code and read nothing from ``input/``.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project


def _build(members, income):
    """A minimal MFJ couple with two IRAs and cash, no COLA/inflation.

    The Social Security "funding discount" (the modelled ~2032 trust-fund
    shortfall) is switched off so the pinned benefit figures are the pure
    SSA-formula amounts, not amounts scaled by that separate haircut.
    """
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
    c = ensure_engine_config(c, source="test_200")
    c["roth_policy"] = "none"
    c["roth_optimized_policy"] = "none"
    c["ss_funding_discount_pct"] = 0.0
    return c


def _ss_by_year(c):
    return {r["year"]: (round(r["h_ss"], 2), round(r["w_ss"], 2)) for r in project(c)}


# Two 1964-born spouses (FRA 67). Used by the timing-gate and no-top-up cases.
_MEMBERS_SAME_AGE = [
    {"name": "Alex", "nickname": "Alex", "dob_year": 1964, "dob_month": 1,
     "retirement_year": 2026, "mortality_age": 95},
    {"name": "Blair", "nickname": "Blair", "dob_year": 1964, "dob_month": 1,
     "retirement_year": 2026, "mortality_age": 95},
]


class SpousalExcessTimingGateTests(unittest.TestCase):
    def test_low_earner_gets_own_only_until_high_earner_files_then_steps_up(self):
        """62/70 split. Alex (worker, PIA 3,400) delays to 70; Blair (PIA 1,200)
        claims at 62.

        Blair's own reduced benefit at 62 (60 months before FRA 67): factor
        1 - 36*(5/9%) - 24*(5/12%) = 1 - 0.20 - 0.10 = 0.70, so 1,200*0.70 =
        840/mo = 10,080/yr.

        Alex files at 70 in 2034 (both born 1964). Only then is Blair owed the
        excess: 0.5*3,400 - 1,200 = 500/mo, and because Blair is 70 when the
        spousal benefit first becomes payable (past FRA), the excess is NOT
        reduced -> 500/mo. Blair's total steps to (840 + 500)*12 = 16,080/yr.

        Alex's own at 70 (36 months of delayed credits): 3,400*1.24 = 4,216/mo
        = 50,592/yr, with no spousal excess (half of Blair's PIA is below Alex's
        own PIA)."""
        income = {"earned_income": 0.0, "h_ss_pia": 3_400.0, "w_ss_pia": 1_200.0,
                  "h_ss_claim_age": 70, "w_ss_claim_age": 62}
        ss = _ss_by_year(_build(_MEMBERS_SAME_AGE, income))

        # Before Alex files: Blair own-only, Alex nothing.
        for year in range(2026, 2034):
            self.assertEqual(ss[year], (0.0, 10_080.0),
                             msg=f"{year}: expected own-only before worker files")
        # 2034 onward: Blair steps up to own + full (unreduced) excess.
        for year in range(2034, 2041):
            self.assertEqual(ss[year], (50_592.0, 16_080.0),
                             msg=f"{year}: expected own + excess after worker files")

    def test_excess_is_reduced_on_the_spousal_schedule_when_claimed_before_fra(self):
        """Reduced-excess case that also exercises a one-year timing gap.

        Blair (born 1966, PIA 1,200) claims own at 62 -> files 2028. Alex
        (born 1965, worker, PIA 3,400) claims at 64 -> files 2029. So in 2028
        Blair receives own-only; the excess begins in 2029 when Alex files.

        Blair's spousal first becomes payable in 2029 at age 63 (48 months
        before FRA 67). The EXCESS reduction is the spousal schedule:
        36*(25/36%) + 12*(5/12%) = 25% + 5% = 30% -> factor 0.70. (Note the
        own-benefit schedule would give 0.75 at 48 months; the excess uses the
        distinct spousal schedule.) Unreduced excess = 0.5*3,400 - 1,200 = 500,
        reduced to 350/mo. Blair own at 62 = 840/mo, so total (840 + 350)*12 =
        14,280/yr.

        Alex own at 64 (36 months early): 3,400*0.80 = 2,720/mo = 32,640/yr."""
        members = [
            {"name": "Alex", "nickname": "Alex", "dob_year": 1965, "dob_month": 1,
             "retirement_year": 2026, "mortality_age": 95},
            {"name": "Blair", "nickname": "Blair", "dob_year": 1966, "dob_month": 1,
             "retirement_year": 2026, "mortality_age": 95},
        ]
        income = {"earned_income": 0.0, "h_ss_pia": 3_400.0, "w_ss_pia": 1_200.0,
                  "h_ss_claim_age": 64, "w_ss_claim_age": 62}
        ss = _ss_by_year(_build(members, income))

        self.assertEqual(ss[2027], (0.0, 0.0))          # neither has claimed
        self.assertEqual(ss[2028], (0.0, 10_080.0))     # Blair own-only, Alex not filed
        for year in range(2029, 2041):
            self.assertEqual(ss[year], (32_640.0, 14_280.0),
                             msg=f"{year}: own + reduced excess after worker files")


class SpousalExcessNoTopUpTests(unittest.TestCase):
    def test_no_top_up_when_own_pia_meets_or_exceeds_half_the_workers(self):
        """Two similar high earners: Alex PIA 3,000, Blair PIA 2,800, both at 62.

        Half of each worker's PIA (1,500 and 1,400) is below the other's own
        PIA, so the excess is zero for BOTH at every age -- each receives only
        their own reduced (age-62, factor 0.70) benefit for life:
        3,000*0.70*12 = 25,200 and 2,800*0.70*12 = 23,520. This is the case a
        planner sanity-checks: dual high earners never receive a spousal top-up.
        """
        income = {"earned_income": 0.0, "h_ss_pia": 3_000.0, "w_ss_pia": 2_800.0,
                  "h_ss_claim_age": 62, "w_ss_claim_age": 62}
        ss = _ss_by_year(_build(_MEMBERS_SAME_AGE, income))
        for year in range(2026, 2041):
            self.assertEqual(ss[year], (25_200.0, 23_520.0),
                             msg=f"{year}: neither spouse should receive any top-up")


if __name__ == "__main__":
    unittest.main()
