"""W3-01 / FIN-008: the Illinois 1.5% S-corp replacement tax reduces the distribution."""
from __future__ import annotations

import unittest

from src.projection_stages.income import IL_REPLACEMENT_TAX_EXEMPTION, _scorp_replacement_tax


class ScorpReplacementTaxUnit(unittest.TestCase):
    def test_illinois_rate_applies_to_base_less_exemption(self):
        c = {"state": "Illinois", "scorp_state_rate": 0.015}
        self.assertAlmostEqual(_scorp_replacement_tax(c, 2026, 226_030.0), 3_375.45, places=2)
        self.assertEqual(IL_REPLACEMENT_TAX_EXEMPTION, 1_000.0)

    def test_other_state_or_zero_rate_or_tiny_base_is_zero(self):
        self.assertEqual(_scorp_replacement_tax({"state": "Texas", "scorp_state_rate": 0.015}, 2026, 100_000.0), 0.0)
        self.assertEqual(_scorp_replacement_tax({"state": "Illinois", "scorp_state_rate": 0.0}, 2026, 100_000.0), 0.0)
        self.assertEqual(_scorp_replacement_tax({"state": "Illinois", "scorp_state_rate": 0.015}, 2026, 500.0), 0.0)

    def test_residency_schedule_controls_the_year(self):
        c = {"state": "Illinois", "scorp_state_rate": 0.015,
             "residency_schedule": [{"state": "Illinois", "start_year": 2026, "end_year": 2026},
                                    {"state": "Florida", "start_year": 2027, "end_year": 2100}]}
        self.assertGreater(_scorp_replacement_tax(c, 2026, 50_000.0), 0.0)
        self.assertEqual(_scorp_replacement_tax(c, 2027, 50_000.0), 0.0)


if __name__ == "__main__":
    unittest.main()
