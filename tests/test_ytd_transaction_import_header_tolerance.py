"""Ticket 279: transaction import rejected valid files and would not say why.

The header check demanded an exact, ordered, case-sensitive match against all
nine columns and, on failure, echoed only the EXPECTED header. It never showed
what it actually received, so a user staring at
``{"errors":["CSV header must exactly match: Date, Merchant, ..."],"received":0}``
could not tell whether their file had a stray column, a renamed one, a
different order, or different capitalization.

Two changes, tested here:

1. Accept what is unambiguously the right file -- any column ORDER, any CASE,
   surrounding whitespace, extra columns, and absent OPTIONAL columns.
   ``normalize_transaction`` already fills missing keys with "", so the strict
   header gate was the only thing rejecting these.
2. When it does fail, say what is wrong: the header received, the required
   columns that are missing, and nothing else.

Only Date and Amount are treated as required: they are the two fields the
importer cannot invent, and every other column is descriptive or mapped later
(unmapped categories already have a documented downstream path).
"""

from __future__ import annotations

import unittest

from src.ytd_tracking import TRANSACTION_COLUMNS, load_transactions_from_csv_text


CANONICAL = ",".join(TRANSACTION_COLUMNS)
ROW = "2026-03-04,Kroger,Groceries,Checking,POS PURCHASE,,-52.10,,Member_1"


class HeaderToleranceTests(unittest.TestCase):

    def test_canonical_header_still_works(self):
        rows, errors = load_transactions_from_csv_text(f"{CANONICAL}\n{ROW}\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Merchant"], "Kroger")
        self.assertEqual(float(rows[0]["Amount"]), -52.10)

    def test_case_and_whitespace_differences_are_accepted(self):
        header = " date , MERCHANT ,category,Account,Original Statement,Notes,amount,Tags,owner"
        rows, errors = load_transactions_from_csv_text(f"{header}\n{ROW}\n")
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["Merchant"], "Kroger")
        self.assertEqual(rows[0]["Owner"], "Member_1")

    def test_column_order_does_not_matter(self):
        rows, errors = load_transactions_from_csv_text(
            "Amount,Date,Merchant\n-52.10,2026-03-04,Kroger\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["Date"], "2026-03-04")
        self.assertEqual(rows[0]["Merchant"], "Kroger")
        self.assertEqual(float(rows[0]["Amount"]), -52.10)

    def test_optional_columns_may_be_absent(self):
        """The common real-world case: an export without Tags/Owner/Notes."""
        rows, errors = load_transactions_from_csv_text(
            "Date,Merchant,Category,Account,Amount\n2026-03-04,Kroger,Groceries,Checking,-52.10\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["Tags"], "")
        self.assertEqual(rows[0]["Owner"], "")

    def test_extra_columns_are_ignored_not_fatal(self):
        rows, errors = load_transactions_from_csv_text(
            "Date,Merchant,Amount,Reference,Balance\n2026-03-04,Kroger,-52.10,XYZ123,900.00\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(float(rows[0]["Amount"]), -52.10)
        self.assertNotIn("Reference", rows[0])

    def test_missing_required_column_names_what_is_missing_and_what_was_received(self):
        """The diagnostic failure this ticket is really about."""
        rows, errors = load_transactions_from_csv_text(
            "Date,Merchant,Category\n2026-03-04,Kroger,Groceries\n"
        )
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        msg = errors[0]
        self.assertIn("Amount", msg)                     # what is missing
        self.assertIn("Date, Merchant, Category", msg)   # what was received
        # And it must not just recite the full expected list as the old one did.
        self.assertIn("missing", msg.lower())

    def test_bom_prefixed_header_still_accepted(self):
        """Pre-existing guard (Excel exports); kept working by the rewrite."""
        rows, errors = load_transactions_from_csv_text(f"﻿{CANONICAL}\n{ROW}\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)

    def test_empty_text_reports_the_empty_case_not_a_header_mismatch(self):
        rows, errors = load_transactions_from_csv_text("")
        self.assertEqual(rows, [])
        self.assertIn("empty", errors[0].lower())

    def test_duplicate_column_names_are_reported_rather_than_silently_collapsed(self):
        """csv.DictReader keeps only the last value for a repeated name, so a
        file with two 'Amount' columns would import the wrong number silently."""
        rows, errors = load_transactions_from_csv_text(
            "Date,Amount,Amount\n2026-03-04,-52.10,999.00\n"
        )
        self.assertEqual(rows, [])
        self.assertTrue(any("duplicate" in e.lower() for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
