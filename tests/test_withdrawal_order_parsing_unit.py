"""Unit coverage for parse_account_draw_priority (src/parsing/withdrawal_order.py).

Ticket 312 flagged this as the one section of the five parse_client()
extractions with a real coverage gap: no dedicated backend test exercised
c['account_draw_priority'] before this extraction (only a frontend .mjs
test, tests/frontend/withdrawal_other_rows.test.mjs, touched the
"Account Order" marker string). See
docs/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
section 5, "Test coverage check".

These assert the dict shape and int-coercion/skip-on-blank behavior
directly against the extracted function, plus an integration check that
src.data_io.parse_client still produces the same field via the re-export.
"""
from __future__ import annotations

import unittest

from src.parsing.withdrawal_order import parse_account_draw_priority


class ParseAccountDrawPriorityTests(unittest.TestCase):
    def test_no_section_returns_empty_dict(self):
        self.assertEqual(
            parse_account_draw_priority({}),
            {'account_draw_priority': {}},
        )

    def test_empty_account_order_subsection_returns_empty_dict(self):
        data = {'Withdrawal Policy': {'Account Order': {}}}
        self.assertEqual(
            parse_account_draw_priority(data),
            {'account_draw_priority': {}},
        )

    def test_parses_int_priorities_keyed_by_account_id(self):
        data = {
            'Withdrawal Policy': {
                'Account Order': {
                    'Alice_Trad_IRA': '1',
                    'Bob_Roth_IRA': '2',
                    'Joint_Taxable_Brokerage': '3',
                }
            }
        }
        result = parse_account_draw_priority(data)
        self.assertEqual(
            result['account_draw_priority'],
            {
                'Alice_Trad_IRA': 1,
                'Bob_Roth_IRA': 2,
                'Joint_Taxable_Brokerage': 3,
            },
        )

    def test_coerces_float_like_strings_and_strips_whitespace_in_ids(self):
        data = {
            'Withdrawal Policy': {
                'Account Order': {
                    '  Alice_Trad_IRA  ': '1.0',
                }
            }
        }
        result = parse_account_draw_priority(data)
        self.assertEqual(result['account_draw_priority'], {'Alice_Trad_IRA': 1})

    def test_blank_priority_values_are_skipped(self):
        data = {
            'Withdrawal Policy': {
                'Account Order': {
                    'Alice_Trad_IRA': '',
                    'Bob_Roth_IRA': '   ',
                    'Joint_Taxable_Brokerage': None,
                    'Cash_Reserve': '2',
                }
            }
        }
        result = parse_account_draw_priority(data)
        self.assertEqual(result['account_draw_priority'], {'Cash_Reserve': 2})

    def test_unparseable_priority_values_are_skipped_not_raised(self):
        data = {
            'Withdrawal Policy': {
                'Account Order': {
                    'Alice_Trad_IRA': 'not-a-number',
                    'Bob_Roth_IRA': '5',
                }
            }
        }
        result = parse_account_draw_priority(data)
        self.assertEqual(result['account_draw_priority'], {'Bob_Roth_IRA': 5})

    def test_missing_withdrawal_policy_section_is_safe(self):
        data = {'Some Other Section': {'x': {'y': 'z'}}}
        self.assertEqual(
            parse_account_draw_priority(data),
            {'account_draw_priority': {}},
        )


class ParseClientReExportIntegrationTests(unittest.TestCase):
    def test_data_io_reexports_same_function(self):
        from src.data_io import parse_account_draw_priority as reexported
        self.assertIs(reexported, parse_account_draw_priority)

    def test_parse_client_wires_account_draw_priority_through(self):
        import copy
        from pathlib import Path

        from conftest import TEST_INPUT_DIR
        from src.data_io import load_csv, parse_client

        data = copy.deepcopy(load_csv(TEST_INPUT_DIR / "client_data.csv"))
        data.setdefault('Withdrawal Policy', {})['Account Order'] = {
            'Alice_Trad_IRA': '1',
        }
        c = parse_client(data, "")
        self.assertIn('account_draw_priority', c)
        self.assertEqual(c['account_draw_priority'].get('Alice_Trad_IRA'), 1)


if __name__ == '__main__':
    unittest.main()
