"""Item 182: Medicare / pre-65 bridge premiums should be prorated by month in
the calendar year a person turns 65, instead of billing a full 12 months of
Medicare (or a full 12 months of pre-65 bridge) based on a hard binary age
gate.

This client: Patricia ("Pat", member_2) was born 5/30/1961, so she turns 65 in
May 2026 (age 65 = 2026 - 1961). Medicare Part B/D/G eligibility begins the
1st of the birth month (standard CMS rule), so in 2026 she should be billed:
  - 8 months of Medicare Part B/D/G (May-Dec), and
  - 4 months of pre-65 bridge premium (Jan-Apr).
Matthew ("Matt", member_1) was born 8/3/1962 and turns 65 in 2027, so his
birth month has no effect on the 2026 row.

Target: the client's stated 2026 total wellness premium
(bridge + Part B + Part D + Part G, i.e. row['wellness_premiums_yr']) is
$22,173.30.
"""
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client
from src.planning_engines import project

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return c


class MedicareProrationTests(unittest.TestCase):
    def test_dob_month_parsed_from_household_input(self):
        c = sample_config()
        # Matt (member_1): 8/3/1962 -> birth month 8.
        self.assertEqual(c['h_dob_yr'], 1962)
        self.assertEqual(c.get('h_dob_month'), 8)
        # Pat (member_2): 5/30/1961 -> birth month 5.
        self.assertEqual(c['w_dob_yr'], 1961)
        self.assertEqual(c.get('w_dob_month'), 5)

    def test_2026_wellness_premium_is_prorated_not_binary(self):
        c = sample_config()
        rows = project(c)
        row = next(r for r in rows if r['year'] == 2026)

        # Pat turns 65 in 2026 (age 65 = 2026 - 1961) -- this is the
        # transition year the proration logic must handle.
        self.assertEqual(row['w_age'], 65)
        self.assertEqual(row['h_age'], 64)

        total = row['wellness_premiums_yr']

        # The old binary-gate engine would have billed Pat a full 12 months
        # of Medicare Part B/D/G and zero pre-65 bridge in 2026:
        #   12 * (446.30 + 174.61 + 359.10) = $11,760.12
        # A month-prorated engine must NOT reproduce that exact figure for a
        # person who turns 65 mid-year.
        old_binary_total = 12 * (446.30 + 174.61 + 359.10)
        self.assertNotAlmostEqual(total, old_binary_total, places=2)

        # Client's stated target for the 2026 total wellness premium.
        target = 22173.30
        try:
            self.assertAlmostEqual(total, target, delta=1.0)
        except AssertionError:
            breakdown = (
                f"wellness_bridge_premium={row.get('wellness_bridge_premium')!r}, "
                f"medicare_base_premium (Part B+D)={row.get('medicare_base_premium')!r}, "
                f"medicare_part_g_premium={row.get('medicare_part_g_premium')!r}, "
                f"wellness_premiums_yr={total!r}"
            )
            raise AssertionError(
                f"2026 wellness_premiums_yr={total} does not match client target "
                f"${target} (delta={total - target:.2f}). Component breakdown: "
                f"{breakdown}. NOTE: with the household's real member_1_retirement_date "
                "(2027-01-01), Matt's own pre-65 bridge premium is gated off in 2026 "
                "(year < h_ret_yr) under existing, pre-item-182 retirement-gate logic "
                "unrelated to the age/month proration fix, so only Pat's prorated "
                "premium is billed this year."
            )


if __name__ == '__main__':
    unittest.main()
