"""The Roth optimizer's discount rate defaults to a nominal 6.5%, not inflation.

`roth_tax_discount_rate` is applied to NOMINAL cash flows -- lifetime tax,
estate tax, the ACA PTC loss, and the terminal-wealth component are all
projected in nominal dollars -- so the rate itself has to be nominal.

It previously defaulted to `c['inf']` (2.5%). Dividing nominal flows by
inflation is a pure deflator: it restates the objective in today's purchasing
power and applies NO time preference on top, i.e. a 0% real discount rate.
That systematically under-rewards locking in current tax rates, because future
tax savings were discounted more slowly than the portfolio that generates them
compounds.

The default is now 6.5% nominal -- roughly the expected long-run portfolio
return, which is the rate at which a dollar handed to the IRS today would
otherwise have grown.

Note what did NOT change: the inflation assumption. `c['inf']` is untouched;
only the discount rate's fallback TO it is removed. The two were never the
same quantity, and coupling them meant editing an inflation assumption
silently retuned the optimizer's time preference.
"""

from __future__ import annotations

import unittest

from src.data_io import DEFAULT_ROTH_TAX_DISCOUNT_RATE, parse_client


class RothDiscountRateDefaultTests(unittest.TestCase):

    def test_default_is_nominal_six_and_a_half_percent(self):
        self.assertAlmostEqual(DEFAULT_ROTH_TAX_DISCOUNT_RATE, 0.065, places=10)

    def test_default_does_not_track_inflation(self):
        """The coupling this change removes.

        Two plans with different inflation assumptions and no explicit discount
        rate must land on the same discount rate. Before, changing inflation
        moved the optimizer's time preference as a side effect.
        """
        rates = []
        for inf in ("2.00%", "3.50%"):
            data = {"Economic Assumptions": {"": {"inflation_general": inf}}}
            c = parse_client(data, "")
            rates.append(c["roth_tax_discount_rate"])
        self.assertEqual(rates[0], rates[1])
        self.assertAlmostEqual(rates[0], 0.065, places=10)

    def test_explicit_plan_value_still_wins(self):
        """A household that has chosen a rate keeps it -- this changes the
        DEFAULT, not stored plans."""
        data = {
            "Withdrawal Policy": {"Roth Conversion": {"roth_tax_discount_rate": "5.00%"}},
        }
        c = parse_client(data, "")
        self.assertAlmostEqual(c["roth_tax_discount_rate"], 0.05, places=10)

    def test_engine_fallback_matches_the_parse_default(self):
        """planning_engines has its own fallback for configs that never went
        through parse_client. The two must not drift apart -- that is how the
        objective would silently score against a different rate than the plan
        page shows."""
        from src.planning_engines import _roth_discount_rate

        self.assertAlmostEqual(_roth_discount_rate({}), 0.065, places=10)
        # Still respects an inflation-free explicit value.
        self.assertAlmostEqual(
            _roth_discount_rate({"roth_tax_discount_rate": 0.07}), 0.07, places=10
        )
        # And an explicit rate wins over any inflation assumption present.
        self.assertAlmostEqual(
            _roth_discount_rate({"roth_tax_discount_rate": 0.04, "inf": 0.03}), 0.04,
            places=10,
        )

    def test_inflation_assumption_itself_is_untouched(self):
        data = {"Economic Assumptions": {"": {"inflation_general": "3.50%"}}}
        c = parse_client(data, "")
        self.assertAlmostEqual(c["inf"], 0.035, places=10)


if __name__ == "__main__":
    unittest.main()
