"""Wave 4 item 4.6 (system review P10 second half): inflate the CA/NY
graduated state-tax brackets by brk_inf, the same way compute_fed_tax already
inflates the federal brackets. Before this fix, _STATE_INCOME_BRACKETS was a
frozen current-law table applied to every projected year unchanged, so a
30-year CA/NY projection showed the effective state rate creeping upward
purely from stale thresholds, not from any real law change or income growth
beyond what inflation already explains.

50-state table expansion is explicitly out of scope (system review §7.3-4
decision: client base confined to the eleven modeled states); only the
CA/NY bracket-inflation half of item 4.6 is implemented here.
"""
from __future__ import annotations

import unittest

from src.core import TAX_BASE_YEAR, state_income_tax


class StateBracketInflationTests(unittest.TestCase):
    def test_ca_effective_rate_stays_flat_when_income_and_brackets_inflate_together(self):
        brk_inf = 0.02
        base_income = 300_000.0
        year0 = TAX_BASE_YEAR
        tax0 = state_income_tax(
            'California', earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
            investment_inc=base_income, nonqual_annuity=0.0, roth_conv=0.0,
            year=year0, age_over_65=True, filing='MFJ', brk_inf=brk_inf,
        )
        income30 = base_income * (1.0 + brk_inf) ** 30
        tax30 = state_income_tax(
            'California', earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
            investment_inc=income30, nonqual_annuity=0.0, roth_conv=0.0,
            year=year0 + 30, age_over_65=True, filing='MFJ', brk_inf=brk_inf,
        )
        rate0 = tax0 / base_income
        rate30 = tax30 / income30
        self.assertLess(abs(rate30 - rate0), 0.01, f"effective CA rate drifted: year0={rate0:.4f} year30={rate30:.4f}")

    def test_frozen_brackets_would_have_drifted_upward_confirming_the_bug_this_fixes(self):
        brk_inf = 0.02
        base_income = 300_000.0
        year0 = TAX_BASE_YEAR
        tax0 = state_income_tax(
            'California', earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
            investment_inc=base_income, nonqual_annuity=0.0, roth_conv=0.0,
            year=year0, age_over_65=True, filing='MFJ', brk_inf=brk_inf,
        )
        income30 = base_income * (1.0 + brk_inf) ** 30
        tax30_frozen = state_income_tax(
            'California', earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
            investment_inc=income30, nonqual_annuity=0.0, roth_conv=0.0,
            year=year0 + 30, age_over_65=True, filing='MFJ', brk_inf=0.0,
        )
        rate0 = tax0 / base_income
        rate30_frozen = tax30_frozen / income30
        self.assertGreater(rate30_frozen, rate0 + 0.01, "frozen brackets should show material upward creep vs. the inflated-bracket baseline")

    def test_ny_brackets_also_inflate(self):
        year0 = TAX_BASE_YEAR
        income = 500_000.0
        tax_now = state_income_tax(
            'New York', earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
            investment_inc=income, nonqual_annuity=0.0, roth_conv=0.0,
            year=year0, age_over_65=True, filing='MFJ', brk_inf=0.02,
        )
        tax_later_same_nominal_income = state_income_tax(
            'New York', earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
            investment_inc=income, nonqual_annuity=0.0, roth_conv=0.0,
            year=year0 + 20, age_over_65=True, filing='MFJ', brk_inf=0.02,
        )
        # Same nominal income, brackets inflated forward 20 years -> less of
        # it should be taxed at the top marginal rates than at year0.
        self.assertLess(tax_later_same_nominal_income, tax_now)

    def test_flat_rate_state_is_unaffected_by_brk_inf(self):
        year0 = TAX_BASE_YEAR
        kwargs = dict(earned=0.0, retirement_dist=50_000.0, ss_taxable=0.0,
                      investment_inc=20_000.0, nonqual_annuity=0.0, roth_conv=0.0,
                      age_over_65=True, filing='MFJ')
        tax_a = state_income_tax('Illinois', year=year0, brk_inf=0.02, **kwargs)
        tax_b = state_income_tax('Illinois', year=year0 + 30, brk_inf=0.02, **kwargs)
        # Illinois is flat-rate; only the raw dollar inputs matter, not brk_inf/year.
        self.assertAlmostEqual(tax_a, tax_b, places=6)

    def test_zero_years_elapsed_is_unaffected_by_brk_inf(self):
        year0 = TAX_BASE_YEAR
        kwargs = dict(earned=0.0, retirement_dist=0.0, ss_taxable=0.0,
                      investment_inc=300_000.0, nonqual_annuity=0.0, roth_conv=0.0,
                      age_over_65=True, filing='MFJ', year=year0)
        tax_default = state_income_tax('California', **kwargs)
        tax_zero_inf = state_income_tax('California', brk_inf=0.0, **{k: v for k, v in kwargs.items()})
        self.assertAlmostEqual(tax_default, tax_zero_inf, places=6)


if __name__ == "__main__":
    unittest.main()
