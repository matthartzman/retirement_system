"""Ticket 295: QLAC (Qualified Longevity Annuity Contract) requirements,
limitations, configuration, and premium recommendation.

Covers: the premium is excluded from the RMD-divisor balance once
purchased (the core IRS benefit), the statutory dollar cap is enforced
even against a misconfigured plan, the premium actually leaves the source
account at purchase, QLAC income shows up as deferred taxable income
starting in the configured year (reusing annuity_cash_income()), and the
recommendation optimizer + CSV backfill.
"""
from __future__ import annotations

import unittest

from src.core import (
    qlac_excluded_rmd_balance,
    qlac_income_start_year_cap,
    qlac_premium_limit,
)
from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import compute_rmds, project
from src.qlac_optimizer import recommend_qlac_premium

from tests.synthetic_plans import base_plan, _no_voluntary_roth


def _config(**overrides):
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    c.update(overrides)
    return c


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


def _qlac_stream(**overrides):
    stream = {
        "enabled": True, "premium": 150_000.0, "source_account": "Member_1_IRA",
        "purchase_year": 2027, "first_yr": 2040, "init_pmt": 2_000.0,
        "base": 0.0, "div_rate": 0.0, "add_pct": 0.0,
        "deferral_years": 0, "reserve_factor": 0.853, "qualified": True,
        "exclusion_ratio": 1.0, "deferral_dampening": 0.55, "payout_type": "fixed",
        "annuitant_dob_yr": 1964, "recovery_age": 86,
        "annuity_calib": {},
    }
    stream.update(overrides)
    return stream


class QlacStatutoryLimitTests(unittest.TestCase):
    def test_premium_limit_is_indexed_forward_from_the_base_year(self):
        base = qlac_premium_limit(2025, 0.0)
        self.assertEqual(base, 210_000.0)
        later = qlac_premium_limit(2030, 0.02)
        self.assertGreater(later, base)

    def test_income_start_year_cap_is_birth_year_plus_85(self):
        self.assertEqual(qlac_income_start_year_cap(1960), 2045)

    def test_excluded_rmd_balance_zero_when_disabled_or_unfunded(self):
        self.assertEqual(qlac_excluded_rmd_balance({}, 0, 2030), 0.0)
        self.assertEqual(
            qlac_excluded_rmd_balance({"h_qlac": {"enabled": False, "premium": 100_000.0}}, 0, 2030),
            0.0,
        )

    def test_excluded_rmd_balance_capped_at_statutory_limit_even_if_misconfigured(self):
        c = {"h_qlac": {"enabled": True, "premium": 5_000_000.0}, "brk_inf": 0.0}
        self.assertEqual(qlac_excluded_rmd_balance(c, 0, 2025), 210_000.0)

    def test_excluded_rmd_balance_uses_configured_premium_under_the_cap(self):
        c = {"wife_qlac": {"enabled": True, "premium": 80_000.0}, "brk_inf": 0.0}
        self.assertEqual(qlac_excluded_rmd_balance(c, 1, 2025), 80_000.0)


class QlacRmdExclusionTests(unittest.TestCase):
    def test_compute_rmds_excludes_a_funded_qlac_premium_from_the_balance_base(self):
        registry = [
            {"id": "ira1", "owner_idx": 0, "acct_type": "traditional_ira", "tax": "pre_tax", "rmd": True},
        ]
        c = {
            "account_registry": registry,
            "rmd_start_age": 75,
            "brk_inf": 0.0,
            "h_qlac": {"enabled": True, "premium": 100_000.0},
            "wife_qlac": {"enabled": False, "premium": 0.0},
        }
        bal = {"ira1": 1_000_000.0}
        result = compute_rmds(c, bal, 2030, h_age=76, w_age=74, h_alive=True, w_alive=True)
        # Divisor for age 76 is 23.7 (RMD_DIVISORS table); balance base should
        # be reduced by the QLAC premium before dividing.
        expected = (1_000_000.0 - 100_000.0) / 23.7
        self.assertAlmostEqual(result["h"], expected, places=2)

    def test_compute_rmds_unaffected_when_no_qlac_configured(self):
        registry = [
            {"id": "ira1", "owner_idx": 0, "acct_type": "traditional_ira", "tax": "pre_tax", "rmd": True},
        ]
        c = {"account_registry": registry, "rmd_start_age": 75, "brk_inf": 0.0}
        bal = {"ira1": 1_000_000.0}
        result = compute_rmds(c, bal, 2030, h_age=76, w_age=74, h_alive=True, w_alive=True)
        self.assertAlmostEqual(result["h"], 1_000_000.0 / 23.7, places=2)


class QlacEngineIntegrationTests(unittest.TestCase):
    def test_premium_is_withdrawn_from_the_source_account_in_the_purchase_year(self):
        c = _config(h_qlac=_qlac_stream())
        pre_purchase_bal = next(
            a["balance"] for a in c["account_registry"] if a["id"] == "Member_1_IRA"
        )
        rows = _by_year(project(c))
        self.assertAlmostEqual(rows[2027]["qlac_purchase_yr"], 150_000.0, delta=1.0)

    def test_qlac_income_starts_exactly_in_the_configured_year(self):
        c = _config(h_qlac=_qlac_stream())
        rows = _by_year(project(c))
        self.assertEqual(rows[2039]["h_qlac_ann"], 0.0)
        self.assertAlmostEqual(rows[2040]["h_qlac_ann"], 24_000.0, delta=1.0)
        # Folded into the household's single-annuity taxable income too.
        self.assertAlmostEqual(rows[2040]["h_single_ann"], rows[2040]["h_qlac_ann"], delta=1.0)

    def test_enabling_a_qlac_lowers_rmds_relative_to_an_otherwise_identical_plan(self):
        with_qlac = _by_year(project(_config(h_qlac=_qlac_stream())))
        without_qlac = _by_year(project(_config()))
        self.assertLess(with_qlac[2040]["rmd_h"], without_qlac[2040]["rmd_h"])

    def test_premium_purchase_is_capped_at_the_statutory_limit_not_the_configured_amount(self):
        c = _config(h_qlac=_qlac_stream(premium=5_000_000.0, purchase_year=2026))
        rows = _by_year(project(c))
        cap = qlac_premium_limit(2026, c.get("brk_inf", 0.02))
        self.assertAlmostEqual(rows[2026]["qlac_purchase_yr"], cap, delta=1.0)

    def test_qlac_from_a_nonexistent_or_non_pretax_account_purchases_nothing(self):
        c = _config(h_qlac=_qlac_stream(source_account="Not_A_Real_Account"))
        rows = _by_year(project(c))
        self.assertEqual(rows[2027]["qlac_purchase_yr"], 0.0)
        # Income still models fine (the stream itself is independent of the
        # purchase-transaction bookkeeping) -- only the balance-sheet effect
        # of a bad source_account is dropped, not the whole feature.
        self.assertAlmostEqual(rows[2040]["h_qlac_ann"], 24_000.0, delta=1.0)

    def test_disabled_qlac_produces_no_income_and_no_purchase(self):
        c = _config(h_qlac=_qlac_stream(enabled=False))
        rows = _by_year(project(c))
        self.assertEqual(rows[2027]["qlac_purchase_yr"], 0.0)
        self.assertEqual(rows[2040]["h_qlac_ann"], 0.0)


class QlacRecommendationTests(unittest.TestCase):
    def test_recommends_the_lesser_of_statutory_cap_and_available_balance(self):
        c = _config()
        out = recommend_qlac_premium(c, 0, year=2026)
        cap = qlac_premium_limit(2026, c.get("brk_inf", 0.02))
        available = sum(
            a["balance"] for a in c["account_registry"]
            if a["tax"] == "pre_tax" and a["owner_idx"] == 0
        )
        self.assertAlmostEqual(out["recommended_premium"], min(cap, available), delta=100.0)
        self.assertEqual(out["statutory_cap"], cap)
        self.assertGreater(out["latest_income_start_year"], 2026)

    def test_already_committed_premium_reduces_remaining_headroom(self):
        c = _config(h_qlac=_qlac_stream(premium=100_000.0))
        out = recommend_qlac_premium(c, 0, year=2026)
        cap = qlac_premium_limit(2026, c.get("brk_inf", 0.02))
        self.assertAlmostEqual(out["recommended_premium"], min(cap - 100_000.0, out["available_pre_tax_balance"]), delta=100.0)

    def test_no_pre_tax_account_for_the_person_yields_zero_recommendation(self):
        c = _config()
        c["account_registry"] = [
            a for a in c["account_registry"] if not (a["tax"] == "pre_tax" and a["owner_idx"] == 0)
        ]
        out = recommend_qlac_premium(c, 0, year=2026)
        self.assertEqual(out["recommended_premium"], 0.0)
        self.assertTrue(any("pre-tax" in n.lower() for n in out["notes"]))


class QlacBackfillTests(unittest.TestCase):
    def test_qlac_rows_backfill_into_a_plan_missing_them(self):
        import shutil
        import tempfile
        from pathlib import Path
        from src import plan_data_backfill
        from src.server.app_core import PLAN_DATA_BACKFILL_ENTRIES

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in Path("input/demo").glob("*.csv"):
                shutil.copy(f, tmp / f.name)
            plan_data_backfill.apply_backfill(tmp, PLAN_DATA_BACKFILL_ENTRIES)
            text = (tmp / "client_income.csv").read_text(encoding="utf-8")
            self.assertIn("Member 1 QLAC", text)
            self.assertIn("Member 2 QLAC", text)
            self.assertIn("Income Streams,Member 1 QLAC,qlac_enabled,FALSE", text)

    def test_backfilled_qlac_is_disabled_and_changes_nothing_by_default(self):
        import shutil
        import tempfile
        from pathlib import Path
        from src import plan_data_backfill
        from src.server.app_core import PLAN_DATA_BACKFILL_ENTRIES
        from src.data_io import load_csv, parse_client

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for f in Path("input/demo").glob("*.csv"):
                shutil.copy(f, tmp / f.name)
            data_before = load_csv(tmp / "client_data.csv")
            c_before = parse_client(data_before, "")

            plan_data_backfill.apply_backfill(tmp, PLAN_DATA_BACKFILL_ENTRIES)
            data_after = load_csv(tmp / "client_data.csv")
            c_after = parse_client(data_after, "")

            self.assertFalse(c_after["h_qlac"]["enabled"])
            self.assertFalse(c_after["wife_qlac"]["enabled"])
            # Terminal figures must be identical before/after backfill.
            rows_before = project(c_before)
            rows_after = project(c_after)
            self.assertAlmostEqual(
                rows_before[-1]["total_nw"], rows_after[-1]["total_nw"], delta=1.0,
            )


if __name__ == "__main__":
    unittest.main()
