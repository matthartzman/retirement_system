"""Pins the cliff's effect on after-tax terminal net worth WITHOUT involving the
optimizer. H1 and H3 ship in one release, so this is what keeps the two effects
attributable if a number later looks wrong."""
import unittest

from src.after_tax import estimate_after_tax_terminal_net_worth, estimate_terminal_hsa_deferred_tax

BASE = {"roth_heir_filing_status": "Single", "brk_inf": 0.0,
        "plan_start": 2026, "plan_end": 2056}
TERMINAL = {"hsa_nw": 400_000.0}

# Fixture for the end-to-end tests below: pretax_nw, taxable balances, and
# trust_nw are all absent/zero, so estimate_after_tax_terminal_net_worth's
# other two haircuts (pretax deferred tax, taxable cap-gain tax) are zero and
# any movement in after_tax_terminal_nw is attributable solely to the HSA
# cliff wired in via hsa["hsa_deferred_tax"].
END_TO_END_TERMINAL = {"total_nw": 1_000_000.0, "hsa_nw": 400_000.0, "year": 2056}


class HsaTerminalCliffTests(unittest.TestCase):
    def test_spouse_beneficiary_leaves_terminal_value_untouched(self):
        out = estimate_terminal_hsa_deferred_tax(dict(BASE, hsa_beneficiary_type="spouse"), TERMINAL)
        self.assertEqual(out["hsa_deferred_tax"], 0.0)
        self.assertEqual(out["terminal_hsa_nw"], 400_000.0)

    def test_non_spouse_beneficiary_takes_a_material_haircut(self):
        out = estimate_terminal_hsa_deferred_tax(dict(BASE, hsa_beneficiary_type="non_spouse"), TERMINAL)
        self.assertGreater(out["hsa_deferred_tax"], 80_000.0,
                           "a $400k lump to a Single heir must cost well over 20%")
        self.assertEqual(out["terminal_hsa_nw"], 400_000.0)

    def test_missing_hsa_in_terminal_is_not_an_error(self):
        out = estimate_terminal_hsa_deferred_tax(dict(BASE, hsa_beneficiary_type="non_spouse"), {})
        self.assertEqual(out["hsa_deferred_tax"], 0.0)

    def test_non_spouse_cliff_actually_reduces_after_tax_terminal_nw(self):
        """End-to-end: exercises estimate_after_tax_terminal_net_worth itself,
        not just the helper, so a regression that drops the cliff from
        total_deferred cannot pass unnoticed."""
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        cliff = estimate_terminal_hsa_deferred_tax(c, END_TO_END_TERMINAL)["hsa_deferred_tax"]
        self.assertGreater(cliff, 0.0, "test fixture must produce a nonzero cliff")

        out = estimate_after_tax_terminal_net_worth(c, END_TO_END_TERMINAL)
        self.assertEqual(out["after_tax_terminal_nw"],
                          END_TO_END_TERMINAL["total_nw"] - cliff)

    def test_spouse_beneficiary_leaves_after_tax_terminal_nw_untouched(self):
        """End-to-end companion to the non-spouse case above: with the same
        minimal fixture (no pretax/taxable/trust balances), a spouse
        beneficiary must leave after_tax_terminal_nw exactly equal to
        total_nw -- no haircut applies at all."""
        c = dict(BASE, hsa_beneficiary_type="spouse")
        out = estimate_after_tax_terminal_net_worth(c, END_TO_END_TERMINAL)
        self.assertEqual(out["after_tax_terminal_nw"], END_TO_END_TERMINAL["total_nw"])
