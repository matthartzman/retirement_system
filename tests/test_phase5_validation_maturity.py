from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _load_engine_config():
    from src.data_io import load_csv
    from src.report_compute import prepare_config_from_sectioned_data
    return prepare_config_from_sectioned_data(load_csv(ROOT / "input" / "client_data.csv"), "", optimize_roth=True)


def _project_metrics(c):
    from src.planning_engines import project
    rows = project(c)
    terminal = rows[-1]
    first = rows[0]
    first_rmd = next((r for r in rows if float(r.get("rmd_total", 0) or 0) > 0), None)
    first_conv = next((r for r in rows if float(r.get("roth_conv", 0) or 0) > 0), None)
    return {
        "plan_start": int(c["plan_start"]),
        "plan_end": int(c["plan_end"]),
        "row_count": len(rows),
        "terminal_year": int(terminal["year"]),
        "terminal_total_nw": round(float(terminal.get("total_nw", 0) or 0), 2),
        "terminal_liquid_nw": round(float(terminal.get("pretax_nw", 0) or 0) + float(terminal.get("roth_nw", 0) or 0) + float(terminal.get("trust_nw", 0) or 0) + float(terminal.get("hsa_nw", 0) or 0), 2),
        "lifetime_tax": round(sum(float(r.get("total_tax", 0) or 0) for r in rows), 2),
        "total_roth_conversion": round(sum(float(r.get("roth_conv", 0) or 0) for r in rows), 2),
        "first_year_total_tax": round(float(first.get("total_tax", 0) or 0), 2),
        "first_rmd_year": int(first_rmd["year"]) if first_rmd else None,
        "first_rmd_total": round(float(first_rmd.get("rmd_total", 0) or 0), 2) if first_rmd else 0,
        "first_conversion_year": int(first_conv["year"]) if first_conv else None,
        "first_conversion_amount": round(float(first_conv.get("roth_conv", 0) or 0), 2) if first_conv else 0,
        "selected_roth_strategy": (c.get("roth_optimization") or {}).get("selected_label", ""),
    }


class Phase5GoldenMasterEngineTests(unittest.TestCase):
    def test_golden_master_library_covers_multiple_plan_stresses(self):
        expected = json.loads((FIXTURES / "golden_master_engine_cases.json").read_text(encoding="utf-8"))
        mutators = {
            "baseline_balanced_couple": lambda c: None,
            "no_voluntary_roth_policy": lambda c: c.update({"roth_policy": "none", "roth_optimized_policy": "none", "roth_optimization": {}}),
            "high_spending_pressure": lambda c: c.update({"spend_base": float(c.get("spend_base", 0)) * 1.20}),
            "lower_return_environment": lambda c: c.update({"ret": 0.04, "ret_stock": 0.055, "ret_bond": 0.03}),
            "early_survivor_compression": lambda c: c.update({"h_death_yr": int(c["plan_start"]) + 5}),
        }
        for case_name, expected_metrics in expected.items():
            with self.subTest(case=case_name):
                c = _load_engine_config()
                mutators[case_name](c)
                actual = _project_metrics(c)
                for key, expected_value in expected_metrics.items():
                    if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                        self.assertAlmostEqual(actual[key], expected_value, delta=1.00, msg=f"{case_name}.{key}")
                    else:
                        self.assertEqual(actual[key], expected_value, f"{case_name}.{key}")


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


@pytest.mark.slow
class Phase5WorkbookSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="phase5_workbook_")
        # Build into an isolated output dir (via RETIREMENT_SYSTEM_OUTPUT_DIR) so
        # this test never overwrites the git-tracked output/retirement_plan.xlsx.
        env = os.environ.copy()
        env["RETIREMENT_SYSTEM_OUTPUT_DIR"] = cls.tmp
        env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
        env["RETIREMENT_MC_SIMS"] = "16"
        env["RETIREMENT_MC_SENSITIVITY_SIMS"] = "3"
        env["RETIREMENT_SKIP_REPORT_SIDECARS"] = "1"
        result = subprocess.run([sys.executable, "tools/build_workbook.py"], cwd=ROOT, text=True, capture_output=True, env=env, timeout=120)
        cls.build_stdout = result.stdout + result.stderr
        if result.returncode != 0:
            raise AssertionError(cls.build_stdout)
        cls.workbook_path = Path(cls.tmp) / "retirement_plan.xlsx"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_workbook_snapshot_sheets_and_key_phrases(self):
        import openpyxl
        snap = json.loads((FIXTURES / "workbook_snapshot_expectations.json").read_text(encoding="utf-8"))
        wb = openpyxl.load_workbook(self.workbook_path, data_only=True, read_only=True)
        for sheet in snap["required_sheets"]:
            self.assertIn(sheet, wb.sheetnames)
        for sheet, phrases in snap["required_phrases"].items():
            text = "\n".join(str(cell) for row in wb[sheet].iter_rows(values_only=True) for cell in row if cell is not None)
            for phrase in phrases:
                self.assertIn(phrase, text, f"{sheet} missing {phrase}")

    def test_workbook_snapshot_rejects_stale_roth_language(self):
        import openpyxl
        snap = json.loads((FIXTURES / "workbook_snapshot_expectations.json").read_text(encoding="utf-8"))
        wb = openpyxl.load_workbook(self.workbook_path, data_only=True, read_only=True)
        combined = "\n".join(
            str(cell)
            for sheet in ["1A. Executive Summary", "4B. Assumptions", "2A. Roth Conversion"]
            if sheet in wb.sheetnames
            for row in wb[sheet].iter_rows(values_only=True)
            for cell in row
            if cell is not None
        )
        for forbidden in snap["forbidden_roth_phrases"]:
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
