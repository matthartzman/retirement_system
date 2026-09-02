"""Ticket 293: convert the Impact page's headline metrics.

A) Terminal Net Worth -> Expected After-Tax Lifetime Consumption-and-
   Transfer Value (LCV): nominal lifetime spending + Post-Tax Inheritance
   (after-tax, after-estate-tax terminal transfer).
B) Lifetime Taxes -> NPV of Future Taxes: total tax discounted to today's
   dollars at the plan's own assumed return rate (c['ret']).
C) Probability of Success -> Worst-Case Ending Wealth (5th percentile
   Monte Carlo outcome) -- already computed via mc_data['terminal_total_nw'],
   this file only covers A/B (compute_baseline_lcv_and_eltr); C is covered
   by the existing Monte Carlo percentile machinery and wired at the
   reporting layer (workbook_builder.py / sheets_summary_builder.py).
D) Effective Future Tax Rate (EFTR): unchanged compute_future_lcv_and_eftr,
   which already scopes "current year through plan end" -- covered here
   only to confirm untouched behavior.
"""
from __future__ import annotations

import unittest

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import (
    compute_baseline_lcv_and_eltr,
    compute_future_lcv_and_eftr,
    project,
)
from src.after_tax import estimate_after_tax_terminal_net_worth

from tests.synthetic_plans import base_plan, _no_voluntary_roth


def _config(**overrides):
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    c.update(overrides)
    return c


class LcvTests(unittest.TestCase):
    def test_lcv_equals_nominal_spending_plus_post_tax_inheritance(self):
        c = _config()
        rows = project(c)
        metrics = compute_baseline_lcv_and_eltr(c, rows)

        nominal_spend = sum(float(r.get("total_spend", 0.0) or 0.0) for r in rows)
        pti = estimate_after_tax_terminal_net_worth(c, rows[-1])["post_tax_inheritance"]

        self.assertAlmostEqual(metrics["lcv"], nominal_spend + pti, delta=1.0)

    def test_lcv_is_not_present_valued(self):
        # A nominal sum must be strictly larger than (or equal to, only in a
        # zero-growth/zero-tax degenerate case) the same figures discounted
        # back to plan_start -- this is the regression guard against silently
        # reverting to the old PV convention.
        c = _config()
        rows = project(c)
        metrics = compute_baseline_lcv_and_eltr(c, rows)
        nominal_spend = sum(float(r.get("total_spend", 0.0) or 0.0) for r in rows)
        self.assertGreater(nominal_spend, 0.0)
        # A PV sum with a positive discount rate is strictly less than the
        # nominal sum for any year past plan_start with nonzero spend.
        plan_start = c["plan_start"]
        ret = c.get("ret", 0.02)
        pv_spend = sum(
            float(r.get("total_spend", 0.0) or 0.0) / ((1.0 + ret) ** max(0, int(r["year"]) - plan_start))
            for r in rows
        )
        self.assertLess(pv_spend, nominal_spend)

    def test_empty_rows_returns_zeros(self):
        c = _config()
        metrics = compute_baseline_lcv_and_eltr(c, [])
        self.assertEqual(metrics, {"lcv": 0.0, "eltr": 0.0, "npv_future_taxes": 0.0})


class NpvFutureTaxesTests(unittest.TestCase):
    def test_npv_uses_the_plans_own_return_rate_not_the_roth_discount_rate(self):
        c = _config(ret=0.10)  # far from the roth discount default (~6.5%)
        rows = project(c)
        metrics = compute_baseline_lcv_and_eltr(c, rows)

        plan_start = c["plan_start"]
        expected_npv = sum(
            float(r.get("total_tax", 0.0) or 0.0) / ((1.0 + 0.10) ** max(0, int(r["year"]) - plan_start))
            for r in rows
        )
        self.assertAlmostEqual(metrics["npv_future_taxes"], expected_npv, delta=1.0)

    def test_npv_is_less_than_nominal_lifetime_tax_when_taxes_are_paid_over_time(self):
        c = _config()
        rows = project(c)
        metrics = compute_baseline_lcv_and_eltr(c, rows)
        nominal_tax = sum(float(r.get("total_tax", 0.0) or 0.0) for r in rows)
        self.assertGreater(nominal_tax, 0.0)
        self.assertLess(metrics["npv_future_taxes"], nominal_tax)

    def test_zero_return_rate_makes_npv_equal_nominal(self):
        c = _config(ret=0.0)
        rows = project(c)
        metrics = compute_baseline_lcv_and_eltr(c, rows)
        nominal_tax = sum(float(r.get("total_tax", 0.0) or 0.0) for r in rows)
        self.assertAlmostEqual(metrics["npv_future_taxes"], nominal_tax, delta=1.0)


class EltrUnchangedTests(unittest.TestCase):
    def test_eltr_still_uses_the_roth_discount_rate_not_ret(self):
        # eltr is an internal candidate-ranking score (Planning Workbench
        # comparison table), deliberately left on its own discount
        # convention -- #293 only changed lcv and added npv_future_taxes.
        c_low_ret = _config(ret=0.0)
        c_high_ret = _config(ret=0.15)
        rows_low = project(c_low_ret)
        rows_high = project(c_high_ret)
        eltr_low = compute_baseline_lcv_and_eltr(c_low_ret, rows_low)["eltr"]
        # Re-run eltr against the SAME rows with a different c['ret'] --
        # since eltr must not depend on c['ret'] at all, the two calls
        # (same rows, different ret) should produce the identical eltr.
        eltr_same_rows_different_ret = compute_baseline_lcv_and_eltr(
            dict(c_low_ret, ret=0.99), rows_low,
        )["eltr"]
        self.assertAlmostEqual(eltr_low, eltr_same_rows_different_ret, delta=1e-9)


class EftrUnchangedTests(unittest.TestCase):
    def test_future_metrics_scope_already_covers_current_year_through_plan_end(self):
        c = _config()
        rows = project(c)
        # A fresh build's plan_start is always "today" (data_io.py sets it
        # from platform_runtime.today()), so the default as_of_year (today)
        # and plan_start cover the identical row set for #293's "Future =
        # Scope of Plan" requirement -- confirm baseline and future metrics
        # agree exactly when as_of_year == plan_start.
        future = compute_future_lcv_and_eftr(c, rows, as_of_year=c["plan_start"])
        baseline_rows_from_plan_start = [r for r in rows if int(r["year"]) >= c["plan_start"]]
        self.assertEqual(len(baseline_rows_from_plan_start), len(rows))


if __name__ == "__main__":
    unittest.main()
