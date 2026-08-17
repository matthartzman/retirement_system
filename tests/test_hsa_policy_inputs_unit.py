import unittest
from src.data_io import load_csv, parse_client
from conftest import TEST_INPUT_DIR


class HsaPolicyInputsTests(unittest.TestCase):
    def test_defaults_are_present_and_conservative(self):
        c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
        self.assertEqual(c["hsa_beneficiary_type"], "spouse")
        self.assertEqual(c["hsa_consume_by"], "second_death_p90")
        self.assertIsNone(c["hsa_expense_bank"])  # None == unlimited
        self.assertEqual(c["hsa_nonqualified_treatment"], "block")

    def test_explicit_zero_bank_is_preserved_not_unlimited(self):
        # A JSON-sourced value of the *integer* 0 (as opposed to the CSV path's
        # string "0", which is truthy and never triggers the bug) must survive
        # as 0.0, not collapse to None ("unlimited") via `_bank or ''`.
        data = load_csv(TEST_INPUT_DIR / "client_data.csv")
        data.setdefault('HSA Policy', {}).setdefault('Withdrawals', {})['hsa_expense_bank'] = 0
        c = parse_client(data, "")
        self.assertIsNotNone(c["hsa_expense_bank"])
        self.assertEqual(c["hsa_expense_bank"], 0.0)
