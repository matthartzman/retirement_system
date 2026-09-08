"""Wave 4 item 4.1 (system review P3): Qualified Charitable Distributions as
an AGI exclusion.

Uses tests/synthetic_plans.py's genuinely-synthetic couple (RMD start age 75,
pre-tax-heavy accounts) with the built-in `_no_voluntary_roth` override, so
QCD's AGI reduction is observed directly rather than absorbed by a
fill-to-bracket Roth optimizer converting more to fill the freed headroom
(a real, separately-correct interaction, but not what this test isolates).
"""
from __future__ import annotations

import copy
import unittest

from src.core import qcd_annual_limit, qcd_eligible_from_year
from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from tests.synthetic_plans import _no_voluntary_roth, base_plan


def _config():
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    return c


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


class QcdEligibilityAndLimitTests(unittest.TestCase):
    def test_eligible_from_year_same_calendar_year_for_jan_jun_birthdays(self):
        self.assertEqual(qcd_eligible_from_year(1960, 1), 2030)
        self.assertEqual(qcd_eligible_from_year(1960, 6), 2030)

    def test_eligible_from_year_pushed_to_next_year_for_jul_dec_birthdays(self):
        self.assertEqual(qcd_eligible_from_year(1960, 7), 2031)
        self.assertEqual(qcd_eligible_from_year(1960, 12), 2031)

    def test_annual_limit_inflates_forward_from_its_base_year(self):
        base = qcd_annual_limit(2025, 0.02)
        later = qcd_annual_limit(2035, 0.02)
        self.assertAlmostEqual(base, 108_000.0, places=2)
        self.assertGreater(later, base)


class QcdAgiExclusionTests(unittest.TestCase):
    def test_baseline_plan_has_no_qcd_activity(self):
        c = _config()
        rows = project(c)
        self.assertFalse(any((r.get("qcd_total_yr") or 0) > 0 for r in rows))

    def test_qcd_reduces_agi_irmaa_tier_ss_taxability_and_niit_while_rmd_is_still_satisfied(self):
        baseline = _by_year(project(_config()))
        rmd_year = next(y for y, r in sorted(baseline.items()) if (r.get("rmd_h") or 0) > 0)
        self.assertGreater(baseline[rmd_year]["rmd_h"], 0)

        c_qcd = _config()
        c_qcd["qcd_enabled"] = True
        c_qcd["h_qcd_annual_amount"] = 1_000_000.0  # deliberately huge; should cap at the RMD/statutory limit
        with_qcd = _by_year(project(c_qcd))

        r0, r1 = baseline[rmd_year], with_qcd[rmd_year]
        applied_qcd = r1["h_qcd_yr"]
        self.assertGreater(applied_qcd, 0)
        self.assertAlmostEqual(applied_qcd, r0["rmd_h"], places=2, msg="QCD should cap at that year's own RMD (phase-1 scope)")

        # RMD is still fully satisfied — gross rmd_h/rmd_w/rmd_total unaffected by QCD.
        self.assertAlmostEqual(r0["rmd_h"], r1["rmd_h"], places=2)
        self.assertAlmostEqual(r0["rmd_total"], r1["rmd_total"], places=2)

        # AGI and everything that reads it must drop.
        self.assertLess(r1["agi"], r0["agi"] - 1.0)
        self.assertLessEqual(r1["irmaa_tier"], r0["irmaa_tier"])
        self.assertLess(r1["ss_taxable"], r0["ss_taxable"] + 1.0)
        self.assertLessEqual(r1["niit"], r0["niit"] + 1e-6)
        self.assertLess(r1["total_tax"], r0["total_tax"])

    def test_qcd_capped_at_statutory_annual_limit_not_just_rmd(self):
        # Give the member a huge RMD-eligible balance (well above the QCD
        # statutory cap) so the binding constraint is the limit, not the RMD.
        c = _config()
        for acct in c.get("account_registry", []):
            if acct.get("id") == "Member_1_IRA":
                acct["balance"] = 5_000_000.0
        c["balances"]["Member_1_IRA"] = 5_000_000.0
        c["qcd_enabled"] = True
        c["h_qcd_annual_amount"] = 1_000_000.0
        rows = _by_year(project(c))
        rmd_year = next(y for y, r in sorted(rows.items()) if (r.get("rmd_h") or 0) > 100_000)
        limit = qcd_annual_limit(rmd_year, c["brk_inf"])
        self.assertAlmostEqual(rows[rmd_year]["h_qcd_yr"], limit, places=2)

    def test_qcd_disabled_flag_is_a_no_op_even_with_amount_configured(self):
        baseline = project(_config())
        c = _config()
        c["qcd_enabled"] = False
        c["h_qcd_annual_amount"] = 50_000.0
        disabled = project(c)
        for r0, r1 in zip(baseline, disabled):
            self.assertAlmostEqual(r0["agi"], r1["agi"], places=2)
            self.assertEqual(r1.get("qcd_total_yr") or 0, 0)

    def test_qcd_end_year_stops_relief_after_the_configured_year(self):
        c = _config()
        c["qcd_enabled"] = True
        c["h_qcd_annual_amount"] = 20_000.0
        rows_open_ended = _by_year(project(c))
        rmd_years = sorted(y for y, r in rows_open_ended.items() if (r.get("rmd_h") or 0) > 0)
        self.assertGreaterEqual(len(rmd_years), 2)
        cutoff = rmd_years[0]
        c["h_qcd_end_year"] = cutoff
        rows_capped = _by_year(project(c))
        self.assertGreater(rows_capped[cutoff]["h_qcd_yr"], 0)
        self.assertEqual(rows_capped[rmd_years[1]]["h_qcd_yr"], 0)


if __name__ == "__main__":
    unittest.main()
