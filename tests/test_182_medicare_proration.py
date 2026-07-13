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

        # Pat's prorated components (the substance of item 182): 8 months of
        # Medicare Part B/D/G + 4 months of pre-65 bridge.
        #   Part B+D+G (8/12): 8 * (446.30 + 174.61 + 359.10) = $7,840.08
        #   Pre-65 bridge (4/12): 12000 * 4/12               = $4,000.00
        self.assertAlmostEqual(row['medicare_base_premium'], 7840.08, delta=0.05)
        self.assertAlmostEqual(row['wellness_bridge_premium'], 4000.00, delta=0.05)

        # Expected 2026 total under the CURRENT modeling decision (retirement
        # gate retained): only Pat is billed, because Matt (member_1) is still
        # employed until his 2027-01-01 retirement date, so his pre-65 bridge
        # premium is $0 in 2026 (employer coverage assumed while working).
        self.assertAlmostEqual(total, 11840.08, delta=0.05)

        # NOTE — client target reconciliation (item 182): the client's stated
        # 2026 target of $22,173.30 assumes (a) Matt is charged a full 12-month
        # pre-65 bridge premium in 2026 despite still working ($12,000), and
        # (b) an ACA Premium Tax Credit of $1,666.78:
        #   7,840.08 (Pat Medicare) + 4,000.00 (Pat bridge)
        #     + 12,000.00 (Matt bridge) - 1,666.78 (ACA PTC) = 22,173.30
        # The engine keeps the retirement gate on the pre-65 bridge, so Matt's
        # premium is $0 until he retires; and the ACA PTC generally will not
        # apply while Matt has 2026 employment income. Enabling Matt's bridge
        # is a one-line change (drop the `year >= *_ret_yr` gate) PENDING the
        # user's confirmation that Matt is on marketplace/COBRA coverage in
        # 2026 rather than employer coverage. If that is confirmed, update the
        # expected total above accordingly.


if __name__ == '__main__':
    unittest.main()
