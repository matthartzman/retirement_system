"""Pins the cliff's effect on after-tax terminal net worth WITHOUT involving the
optimizer. H1 and H3 ship in one release, so this is what keeps the two effects
attributable if a number later looks wrong."""
import unittest

from src.after_tax import estimate_terminal_hsa_deferred_tax

BASE = {"roth_heir_filing_status": "Single", "brk_inf": 0.0,
        "plan_start": 2026, "plan_end": 2056}
TERMINAL = {"hsa_nw": 400_000.0}


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
