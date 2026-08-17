"""The HSA cliff is a single-year lump, which is why the 10-year-rule helper
cannot be reused: effective_heir_ten_year_rate spreads the balance over ten
slices, and that spreading is exactly what an inherited HSA does NOT get."""
import unittest

from src.after_tax import effective_heir_ten_year_rate, hsa_terminal_tax

BASE = {"heir_filing_status": "Single", "brk_inf": 0.0,
        "plan_start": 2026, "plan_end": 2056}


class HsaTerminalTaxTests(unittest.TestCase):
    def test_spouse_beneficiary_owes_nothing(self):
        c = dict(BASE, hsa_beneficiary_type="spouse")
        self.assertEqual(hsa_terminal_tax(c, 500_000.0), 0.0)

    def test_charity_beneficiary_owes_nothing(self):
        c = dict(BASE, hsa_beneficiary_type="charity")
        self.assertEqual(hsa_terminal_tax(c, 500_000.0), 0.0)

    def test_zero_balance_owes_nothing(self):
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        self.assertEqual(hsa_terminal_tax(c, 0.0), 0.0)

    def test_non_spouse_lump_is_taxed_harder_than_a_ten_year_stretch(self):
        """The whole point of the finding. Same balance, same heir: one lump
        climbs into higher brackets than ten slices do."""
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        bal = 500_000.0
        lump = hsa_terminal_tax(c, bal)
        stretch = effective_heir_ten_year_rate(c, bal) * bal
        self.assertGreater(lump, stretch * 1.2,
                           "a single-year lump must cost materially more than a 10-year stretch")

    def test_effective_rate_rises_with_balance(self):
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        small = hsa_terminal_tax(c, 50_000.0) / 50_000.0
        large = hsa_terminal_tax(c, 800_000.0) / 800_000.0
        self.assertGreater(large, small)
