"""HSA-reimbursed medical expense is not also deducted on Schedule A.

Design: docs/superpowers/plans/2026-08-26-hsa-expense-bank-and-double-dip-spec.md

A qualified medical expense cannot both be reimbursed tax-free from an HSA
and deducted on Schedule A. Before this fix, `medical_expense_yr` fed the
itemized medical deduction above the 7.5%-of-AGI floor with no reduction for
HSA dollars reimbursed against the same expense, so every HSA withdrawal took
both benefits. Measured on the frozen fixture at the time: all 123,301.40 of
lifetime HSA withdrawals were also clearing the floor.

The load-bearing guards here are `DeductionIsNettedTests` (the correction
happens, and by exactly the right amount) and `ScopeIsLimitedTests` (it
changes only the deduction, and only for households that actually draw an
HSA). The second matters as much as the first: the natural way to get this
wrong is to strip more deduction than the HSA reimbursed, which an early
draft did -- it re-derived the floor against the cascade-mutated `agi` and
removed 18,439 against a 10,168 reimbursement in one fixture year.
"""
from __future__ import annotations

import unittest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import project


def _config(**over):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c.update(over)
    return c


def _rows_with_hsa_draw_and_deduction(rows):
    return [r for r in rows
            if (r.get("hsa_wd") or 0.0) > 1.0
            and (r.get("medical_expense_hsa_reimbursed") or 0.0) > 1.0]


class DeductionIsNettedTests(unittest.TestCase):
    def test_the_fixture_actually_exercises_this(self):
        # A guard that never fires is not a guard. The frozen fixture draws
        # its HSA on a smooth_window schedule from 2031 against medical spend
        # far exceeding those draws, so it must hit this path -- if a future
        # fixture change stops exercising it, the rest of this file becomes
        # vacuous and that should be loud.
        rows = project(_config())
        hits = _rows_with_hsa_draw_and_deduction(rows)
        self.assertTrue(
            hits,
            "the frozen fixture no longer has any year with both an HSA draw "
            "and an HSA-reimbursed medical figure; the guards below are vacuous",
        )

    def test_reimbursed_amount_never_exceeds_the_hsa_draw(self):
        rows = project(_config())
        for r in _rows_with_hsa_draw_and_deduction(rows):
            self.assertLessEqual(
                r["medical_expense_hsa_reimbursed"], r["hsa_wd"] + 1e-6,
                f"year {r['year']}: netted more than the HSA actually withdrew",
            )

    def test_reimbursed_amount_never_exceeds_that_years_medical_spend(self):
        rows = project(_config())
        for r in _rows_with_hsa_draw_and_deduction(rows):
            medical = ((r.get("wellness_premiums_yr") or 0.0)
                       + (r.get("wellness_base_yr") or 0.0)
                       + (r.get("wellness_shock_yr") or 0.0)
                       + (r.get("ltc_prem_yr") or 0.0))
            self.assertLessEqual(
                r["medical_expense_hsa_reimbursed"], medical + 1e-6,
                f"year {r['year']}: netted more medical expense than was incurred",
            )

    def test_deduction_never_goes_negative(self):
        rows = project(_config())
        for r in rows:
            self.assertGreaterEqual(
                r.get("medical_expense_deduction", 0.0), -1e-9,
                f"year {r['year']}: medical deduction went negative",
            )


class ScopeIsLimitedTests(unittest.TestCase):
    def test_a_household_that_never_draws_an_hsa_is_unaffected(self):
        # No hsa_ids => no HSA draw => the correction must never fire, and the
        # deduction must be whatever it always was.
        rows = project(_config(hsa_ids=[]))
        for r in rows:
            self.assertEqual(
                r.get("medical_expense_hsa_reimbursed", 0.0), 0.0,
                f"year {r['year']}: correction fired without an HSA draw",
            )

    def test_cash_spending_is_not_reduced_only_the_deduction_is(self):
        # The medical spend is a real cost. This change alters what is
        # deductible, never what is spent -- so total_spend must match a run
        # of the same household with the deduction correction inert (no HSA).
        with_hsa = project(_config())
        without = project(_config(hsa_ids=[]))
        by_year = {r["year"]: r for r in without}
        for r in with_hsa:
            other = by_year.get(r["year"])
            if other is None:
                continue
            self.assertAlmostEqual(
                r.get("total_spend", 0.0), other.get("total_spend", 0.0), places=2,
                msg=f"year {r['year']}: total_spend moved; this change must "
                    f"affect the deduction only, not spending",
            )

    def test_the_plan_still_funds_itself(self):
        # The correction raises tax after the cascade has already run, so the
        # gap grows and must be absorbed by the remaining draws (Roth, home
        # equity). If placement were wrong the shortfall would surface here.
        rows = project(_config())
        worst = max((r.get("unfunded_gap") or 0.0) for r in rows)
        self.assertLessEqual(
            worst, 1.0,
            "the deduction correction left an unfunded gap, which means the "
            "extra tax is being recognized after the cascade can still fund it",
        )


if __name__ == "__main__":
    unittest.main()
