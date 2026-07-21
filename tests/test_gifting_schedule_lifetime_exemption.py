"""Wave 4 item 4.8 (system review P11): gifting schedule with lifetime-
exemption tracking. A genuinely new balance-mutating path outside the
withdrawal cascade -- gifted dollars leave the funding account directly and
never fund household spending; amounts above the per-donee annual exclusion
consume federal lifetime exemption, reducing what's available at the second
death.
"""
from __future__ import annotations

import unittest

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from tests.synthetic_plans import _no_voluntary_roth, base_plan


def _config():
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    return c


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


def _gift(**overrides):
    g = {
        'name': 'Gift 1',
        'donor': 'joint',
        'funding_account': 'Joint_Trust',
        'annual_amount_per_donee': 10_000.0,
        'donee_count': 1,
        'start_year': 2026,
        'end_year': 2030,
        'is_appreciated_asset': False,
    }
    g.update(overrides)
    return g


class GiftingScheduleTests(unittest.TestCase):
    def test_no_gifting_schedule_is_a_no_op(self):
        rows = project(_config())
        self.assertTrue(all((r.get('gift_total_yr') or 0) == 0 for r in rows))
        self.assertTrue(all((r.get('lifetime_exemption_used_cumulative') or 0) == 0 for r in rows))

    def test_gift_within_annual_exclusion_consumes_no_lifetime_exemption(self):
        c = _config()
        c['gift_excl'] = 19_000.0
        c['gifting_schedule'] = [_gift(annual_amount_per_donee=10_000.0, donee_count=2, start_year=2026, end_year=2026)]
        rows = _by_year(project(c))
        self.assertAlmostEqual(rows[2026]['gift_total_yr'], 20_000.0, places=2)
        self.assertEqual(rows[2026]['gift_excess_over_exclusion_yr'], 0)
        self.assertEqual(rows[2026]['lifetime_exemption_used_cumulative'], 0)

    def test_gift_above_annual_exclusion_consumes_only_the_excess(self):
        c = _config()
        c['gift_excl'] = 19_000.0
        c['gifting_schedule'] = [_gift(annual_amount_per_donee=25_000.0, donee_count=2, start_year=2026, end_year=2026)]
        rows = _by_year(project(c))
        # (25000 - 19000) * 2 donees = 12000 above the exclusion
        self.assertAlmostEqual(rows[2026]['gift_excess_over_exclusion_yr'], 12_000.0, places=2)
        self.assertAlmostEqual(rows[2026]['lifetime_exemption_used_cumulative'], 12_000.0, places=2)

    def test_lifetime_exemption_used_accumulates_across_years(self):
        c = _config()
        c['gift_excl'] = 19_000.0
        c['gifting_schedule'] = [_gift(annual_amount_per_donee=25_000.0, donee_count=1, start_year=2026, end_year=2028)]
        rows = _by_year(project(c))
        # (25000-19000) = 6000/yr excess
        self.assertAlmostEqual(rows[2026]['lifetime_exemption_used_cumulative'], 6_000.0, places=2)
        self.assertAlmostEqual(rows[2027]['lifetime_exemption_used_cumulative'], 12_000.0, places=2)
        self.assertAlmostEqual(rows[2028]['lifetime_exemption_used_cumulative'], 18_000.0, places=2)
        # gifting stopped after 2028 -> cumulative stays flat, not reset.
        self.assertAlmostEqual(rows[2029]['lifetime_exemption_used_cumulative'], 18_000.0, places=2)

    def test_gifted_dollars_actually_leave_the_funding_account(self):
        baseline = _by_year(project(_config()))
        c = _config()
        c['gifting_schedule'] = [_gift(annual_amount_per_donee=10_000.0, donee_count=1, start_year=2026, end_year=2026)]
        with_gift = _by_year(project(c))
        # Terminal net worth should be lower with a real, unrecovered gift out
        # of the estate (holding the same return/spending assumptions).
        self.assertLess(with_gift[2058]['total_nw'], baseline[2058]['total_nw'])

    def test_gift_is_capped_at_available_funding_account_balance(self):
        c = _config()
        for acct in c.get('account_registry', []):
            if acct.get('id') == 'Joint_Trust':
                acct['balance'] = 5_000.0
        c['balances']['Joint_Trust'] = 5_000.0
        c['gift_excl'] = 19_000.0
        c['gifting_schedule'] = [_gift(annual_amount_per_donee=25_000.0, donee_count=1, start_year=2026, end_year=2026)]
        rows = _by_year(project(c))
        self.assertLessEqual(rows[2026]['gift_total_yr'], 5_000.0 + 1e-6)
        # Excess-over-exclusion should scale down proportionally to what was
        # actually deliverable, not credit exemption use for undelivered gifts.
        self.assertLess(rows[2026]['gift_excess_over_exclusion_yr'], 6_000.0)

    def test_unknown_funding_account_is_a_safe_no_op(self):
        c = _config()
        c['gifting_schedule'] = [_gift(funding_account='Nonexistent_Account', start_year=2026, end_year=2026)]
        rows = _by_year(project(c))
        self.assertEqual(rows[2026]['gift_total_yr'], 0)


class GiftingSchemaAndDataIoTests(unittest.TestCase):
    def test_parse_advanced_modules_reads_gifting_schedule_section(self):
        from src.data_io import parse_advanced_modules
        data = {
            'Gifting Schedule': {
                'Gift 1': {
                    'donor': 'h',
                    'funding_account': 'Joint_Trust',
                    'annual_amount_per_donee': '25000',
                    'donee_count': '2',
                    'start_year': '2026',
                    'end_year': '2030',
                    'is_appreciated_asset': 'TRUE',
                }
            }
        }
        result = parse_advanced_modules(data)
        entry = result['gifting_schedule'][0]
        self.assertEqual(entry['donor'], 'h')
        self.assertEqual(entry['funding_account'], 'Joint_Trust')
        self.assertAlmostEqual(entry['annual_amount_per_donee'], 25000.0)
        self.assertEqual(entry['donee_count'], 2)
        self.assertEqual(entry['start_year'], 2026)
        self.assertEqual(entry['end_year'], 2030)
        self.assertTrue(entry['is_appreciated_asset'])


if __name__ == "__main__":
    unittest.main()
