"""Closed-form unit tests for src/taxes.py and src/core.py's tax math.

Extracted verbatim from tests/test_phase5_validation_maturity.py (system review
2026-08-04, quality finding `buried-tax-math-unit-tests`). src/taxes.py has the
highest fan-in of any domain module in the codebase -- 26 importers -- and had
no test file bearing its name. Its only unit-level coverage lived inside a file
about a "Phase 5" validation-maturity roadmap item, alongside PDF structural
checks and a live-plan diagnostic, none of which relate to tax math. A
developer debugging a bracket or RMD calculation had no discoverable entry
point.

This is coverage relocation, not new numbered-test growth, so it is compatible
with tests/test_freeze_numbered_test_files.py's policy.

Covers: federal bracket edges, standard deduction, IRMAA/NIIT thresholds, IRS
Pub 590-B RMD examples, the Social Security taxability worksheet, and
reconciliation against an independently-coded bracket calculator.
"""
from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class Phase5ClosedFormTaxTests(unittest.TestCase):
    def test_federal_tax_closed_form_bracket_edges(self):
        from src.core import compute_fed_tax
        self.assertAlmostEqual(compute_fed_tax(100000, 2025, "MFJ", 0.0), 11828.00, places=2)
        self.assertAlmostEqual(compute_fed_tax(50000, 2025, "Single", 0.0), 5914.00, places=2)
        self.assertAlmostEqual(compute_fed_tax(206700, 2025, "MFJ", 0.0), 35302.00, places=2)

    def test_standard_deduction_and_state_tax_closed_form(self):
        from src.core import standard_deduction, state_income_tax
        self.assertAlmostEqual(standard_deduction(2025, "MFJ", 0.0, n_over_65=2), 33200.00, places=2)
        self.assertAlmostEqual(standard_deduction(2025, "Single", 0.0, n_over_65=1), 17000.00, places=2)
        il_tax = state_income_tax(
            "Illinois", earned=100000, retirement_dist=100000, ss_taxable=20000,
            investment_inc=10000, nonqual_annuity=5000, roth_conv=50000, year=2025,
            age_over_65=True,
        )
        self.assertAlmostEqual(il_tax, 5692.50, places=2)

    def test_irmaa_and_niit_simple_threshold_behavior(self):
        from src.core import irmaa_surcharge, irmaa_tier
        self.assertEqual(irmaa_tier(200000, 2026, 2026, filing="MFJ"), 0)
        self.assertEqual(irmaa_tier(213000, 2026, 2026, filing="MFJ"), 1)
        self.assertGreater(irmaa_surcharge(213000, 2026, 2026, filing="MFJ"), 0)


class Phase5IRSExampleReconciliationTests(unittest.TestCase):
    def test_irs_style_social_security_examples(self):
        from src.core import social_security_taxable_amount
        examples = json.loads((FIXTURES / "irs_style_examples.json").read_text(encoding="utf-8"))["social_security_taxable_examples"]
        for ex in examples:
            with self.subTest(ex["name"]):
                actual = social_security_taxable_amount(ex["social_security"], ex["other_income"], ex["filing"])
                self.assertAlmostEqual(actual, ex["expected_taxable_social_security"], places=2)

    def test_irs_pub_590b_rmd_examples(self):
        from src.core import rmd_divisor
        examples = json.loads((FIXTURES / "irs_style_examples.json").read_text(encoding="utf-8"))["rmd_examples"]
        for ex in examples:
            with self.subTest(ex["name"]):
                div = rmd_divisor(ex["age"])
                self.assertAlmostEqual(div, ex["expected_divisor"], places=1)
                self.assertAlmostEqual(ex["prior_year_balance"] / div, ex["expected_rmd"], places=2)


class Phase5CrossToolReconciliationTests(unittest.TestCase):
    def _manual_fed_tax(self, filing: str, taxable: float) -> float:
        brackets = {
            "MFJ": [(0, 23850, .10), (23850, 96950, .12), (96950, 206700, .22), (206700, 394600, .24), (394600, 501050, .32), (501050, 751600, .35), (751600, float("inf"), .37)],
            "Single": [(0, 11925, .10), (11925, 48475, .12), (48475, 103350, .22), (103350, 197300, .24), (197300, 250525, .32), (250525, 626350, .35), (626350, float("inf"), .37)],
        }[filing]
        tax = 0.0
        for lo, hi, rate in brackets:
            if taxable <= lo:
                break
            tax += (min(taxable, hi) - lo) * rate
        return tax

    def test_csv_backed_independent_reconciliation_cases(self):
        from src.core import compute_fed_tax, social_security_taxable_amount, rmd_divisor, state_income_tax
        with (FIXTURES / "cross_tool_reconciliation_cases.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                with self.subTest(row["case_id"]):
                    expected = float(row["expected"])
                    tol = float(row["tolerance"])
                    domain = row["domain"]
                    if domain == "federal_tax":
                        filing, taxable, year = row["input_a"], float(row["input_b"]), int(row["input_c"])
                        engine = compute_fed_tax(taxable, year, filing, 0.0)
                        independent = self._manual_fed_tax(filing, taxable)
                    elif domain == "social_security":
                        engine = social_security_taxable_amount(float(row["input_b"]), float(row["input_c"]), row["input_a"])
                        # The independent worksheet-style expected value is supplied in the CSV fixture.
                        independent = expected
                    elif domain == "rmd":
                        engine = float(row["input_b"]) / rmd_divisor(int(row["input_a"]))
                        independent = expected
                    elif domain == "state_tax_il":
                        engine = state_income_tax("Illinois", float(row["input_a"]), 100000, 20000, float(row["input_b"]), float(row["input_c"]), 50000, 2025, True)
                        independent = expected
                    else:
                        raise AssertionError(domain)
                    self.assertAlmostEqual(engine, expected, delta=tol)
                    self.assertAlmostEqual(engine, independent, delta=tol)
