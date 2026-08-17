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
