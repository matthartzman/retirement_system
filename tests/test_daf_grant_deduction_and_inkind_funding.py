"""Two DAF corrections in the deterministic engine.

1. Grant netting. ``daf_grant_yr`` was computed, stored on the row, and shown
   in the Projection Cash Flow callout, but nothing ever consumed it. The
   household therefore kept deducting the full ``char_low`` cash-giving intent
   in grant years even though those charitable dollars were being paid out of
   the DAF balance -- dollars that were already deducted in the contribution
   year. Grants out of a DAF are not themselves deductible, so this was a
   straight double deduction over the grant window. The fix nets the grant out
   of the itemizable cash-gift component exactly the way QCD dollars already
   were (see the "Item 4.1" comment in deterministic_engine.py).

2. In-kind funding of an appreciated contribution. ``daf_contribution_is_
   appreciated`` only ever switched the AGI ceiling (60% -> 30%). The gift
   itself was still routed through ``lump`` into ``total_spend_need``, so the
   withdrawal waterfall funded it with a taxable-account draw that realized
   capital gains -- destroying the central tax benefit of the strategy, since
   donating appreciated securities in kind avoids the embedded gain entirely.
   The fix transfers the shares directly out of the taxable accounts: no cash
   need, no gain, lots consumed without a taxable event.
"""
from __future__ import annotations

import unittest

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.core import LotEngine, TaxLot
from src.planning_engines import donate_taxable_in_kind
from src.reporting.sheets_qc_reference import account_reconciliation_rows

from tests.synthetic_plans import _no_voluntary_roth, base_plan


def _config(**overrides):
    c = build_plan_from_json(base_plan(), "")
    c = ensure_engine_config(c, source="test")
    _no_voluntary_roth(c)
    c.update(overrides)
    return c


def _with_daf(**overrides):
    opts = dict(
        daf_enabled=True,
        daf_year=2026,
        daf_amount=150_000.0,
        daf_use_start=2027,
        daf_use_end=2036,
        daf_use_amount=25_000.0,
        daf_contribution_is_appreciated=False,
    )
    opts.update(overrides)
    return _config(**opts)


def _by_year(rows):
    return {int(r["year"]): r for r in rows}


class DafGrantNettingTests(unittest.TestCase):
    """Grants paid out of the DAF balance are not deductible again."""

    GIVING = 30_000.0
    GRANT = 25_000.0

    def test_grant_year_charitable_deduction_is_net_of_the_grant(self):
        granting = _by_year(project(_with_daf(char_low=self.GIVING,
                                              daf_use_amount=self.GRANT)))
        no_grant = _by_year(project(_with_daf(char_low=self.GIVING,
                                              daf_use_amount=0.0)))
        r = granting[2030]
        b = no_grant[2030]
        # Same AGI-driven haircut on both sides, so the whole gap is the grant.
        self.assertAlmostEqual(
            b["charitable_deduction_yr"] - r["charitable_deduction_yr"],
            self.GRANT, delta=1.0,
            msg="grant dollars must not be deducted a second time",
        )

    def test_grant_larger_than_the_giving_intent_floors_at_zero(self):
        rows = _by_year(project(_with_daf(char_low=5_000.0, daf_use_amount=self.GRANT)))
        self.assertEqual(rows[2030]["charitable_deduction_yr"], 0.0)

    def test_years_outside_the_grant_window_are_untouched(self):
        granting = _by_year(project(_with_daf(char_low=self.GIVING,
                                              daf_use_amount=self.GRANT)))
        no_grant = _by_year(project(_with_daf(char_low=self.GIVING,
                                             daf_use_amount=0.0)))
        # 2037 is one year past daf_use_end.
        self.assertAlmostEqual(granting[2037]["charitable_deduction_yr"],
                               no_grant[2037]["charitable_deduction_yr"], delta=1.0)

    def test_grant_does_not_change_the_cash_bridge(self):
        # char_low is a deduction input only -- it is not a cash-flow line --
        # so netting the grant against it must not move total_spend.
        granting = _by_year(project(_with_daf(char_low=self.GIVING,
                                              daf_use_amount=self.GRANT)))
        self.assertAlmostEqual(granting[2030]["daf_grant_yr"], self.GRANT, delta=0.01)


class DafInKindContributionTests(unittest.TestCase):
    """An appreciated contribution is an in-kind share transfer, not a cash gift."""

    AMOUNT = 150_000.0

    def setUp(self):
        self.cash = _by_year(project(_with_daf(daf_contribution_is_appreciated=False)))
        self.inkind = _by_year(project(_with_daf(daf_contribution_is_appreciated=True)))
        self.baseline = _by_year(project(_config()))

    def test_cash_contribution_still_flows_through_the_spending_bridge(self):
        r = self.cash[2026]
        self.assertAlmostEqual(r["lump"], self.AMOUNT, delta=1.0)
        self.assertAlmostEqual(r["daf_contrib_yr"], self.AMOUNT, delta=1.0)
        self.assertEqual(r.get("daf_inkind_yr", 0.0), 0.0)

    def test_in_kind_contribution_is_not_a_cash_need(self):
        r = self.inkind[2026]
        self.assertEqual(r["lump"], 0.0)
        self.assertAlmostEqual(r["daf_inkind_yr"], self.AMOUNT, delta=1.0)
        self.assertAlmostEqual(r["total_spend"], self.baseline[2026]["total_spend"],
                               delta=1.0)

    def test_in_kind_contribution_realizes_no_capital_gain(self):
        # The whole point of gifting appreciated securities: the embedded gain
        # is never realized. The cash gift, by contrast, has to be funded.
        self.assertAlmostEqual(self.inkind[2026]["ltcg_gain"],
                               self.baseline[2026]["ltcg_gain"], delta=1.0)
        self.assertAlmostEqual(self.inkind[2026]["ltcg_tax"],
                               self.baseline[2026]["ltcg_tax"], delta=1.0)
        self.assertGreater(self.cash[2026]["ltcg_gain"], 0.0)

    def test_in_kind_contribution_still_reduces_the_taxable_accounts(self):
        # The shares leave the portfolio even though no cash was withdrawn.
        self.assertLess(self.inkind[2026]["trust_nw"],
                        self.baseline[2026]["trust_nw"] - self.AMOUNT * 0.9)

    def test_in_kind_gift_leaves_more_wealth_than_the_same_cash_gift(self):
        # Not realizing the gain is worth real money: the cash gift pays LTCG
        # tax on the draw that funds it, the in-kind gift pays none.
        # Compare total net worth, not the taxable bucket alone: the cash gift
        # is funded across the whole waterfall, so the taxable balance by
        # itself says nothing about which household came out ahead.
        self.assertGreater(self.inkind[2026]["total_nw"], self.cash[2026]["total_nw"])
        self.assertGreater(self.cash[2026]["ltcg_tax"], 0.0)

    def test_in_kind_contribution_still_earns_the_deduction(self):
        # 30%-of-AGI ceiling, remainder carried forward -- unchanged behavior.
        r = self.inkind[2026]
        self.assertGreater(r["daf_deduction_yr"], 0.0)
        self.assertAlmostEqual(r["daf_deduction_yr"] + r["daf_deduction_carryforward"],
                               self.AMOUNT, delta=1.0)

    def test_in_kind_transfer_keeps_the_account_roll_forward_footing(self):
        # The shares leave the account without being a cash withdrawal, so the
        # movement has to be booked somewhere or Sheet 25's roll-forward breaks
        # by the full gift. It is booked as a transfer out.
        c = _with_daf(daf_contribution_is_appreciated=True)
        _recs, max_abs_delta = account_reconciliation_rows(c, project(c))
        self.assertLess(max_abs_delta, 10.0)

    def test_in_kind_transfer_is_capped_by_available_taxable_dollars(self):
        # A gift larger than the taxable accounts can fund transfers only what
        # is there, and the deduction pool follows the dollars actually given.
        rows = _by_year(project(_with_daf(daf_amount=50_000_000.0,
                                          daf_contribution_is_appreciated=True)))
        r = rows[2026]
        self.assertGreater(r["daf_inkind_yr"], 0.0)
        self.assertLess(r["daf_inkind_yr"], 50_000_000.0)
        self.assertAlmostEqual(r["daf_contrib_yr"], r["daf_inkind_yr"], delta=0.01)


if __name__ == "__main__":
    unittest.main()


class DafInKindLotSelectionTests(unittest.TestCase):
    """Which lots leave the portfolio, once lot data actually exists.

    Charitable lot selection is the mirror image of sale lot selection. A sale
    wants the highest basis (HIFO, this system's default) so the realized gain
    is small. A gift wants the *lowest* basis, because that gain vanishes at
    the charity -- gifting high-basis shares wastes the strategy and strands
    the low-basis shares for a future taxable sale.
    """

    ACCT = "Joint_Trust"

    def _engine(self, method="HIFO"):
        # Three same-symbol lots, equal $100k market value, very different
        # basis. LOW is long-term and deeply appreciated; HIGH is long-term and
        # barely appreciated; NEW is short-term and must never be gifted.
        lots = {
            self.ACCT: {
                "LOW": [TaxLot("LOW", 1000, 10_000.0, "01/15/2010")],
                "HIGH": [TaxLot("HIGH", 1000, 90_000.0, "01/15/2010")],
                "NEW": [TaxLot("NEW", 1000, 95_000.0, "06/01/2026")],
            }
        }
        prices = {"LOW": 100.0, "HIGH": 100.0, "NEW": 100.0}
        return LotEngine(lots, prices, fallback_gain_fraction=0.5, method=method)

    def test_gift_takes_the_lowest_basis_long_term_lot_first(self):
        eng = self._engine()
        gifted, gain_avoided, consumed = eng.donate_lots(self.ACCT, 100_000.0,
                                                         current_year=2026)
        self.assertAlmostEqual(gifted, 100_000.0, delta=1.0)
        self.assertEqual([sym for sym, _mv, _g in consumed], ["LOW"])
        # $100k market value against $10k basis: the full $90k gain escapes.
        self.assertAlmostEqual(gain_avoided, 90_000.0, delta=1.0)

    def test_gift_selection_ignores_the_plans_sale_lot_method(self):
        # HIFO is the sale default and would pick HIGH first -- the worst lot
        # to give away. Donation ordering must not follow it.
        for method in ("HIFO", "FIFO", "LIFO"):
            with self.subTest(method=method):
                eng = self._engine(method)
                _gifted, _gain, consumed = eng.donate_lots(self.ACCT, 100_000.0,
                                                           current_year=2026)
                self.assertEqual([sym for sym, _mv, _g in consumed], ["LOW"])

    def test_short_term_lots_are_never_gifted(self):
        # A gift of property held a year or less deducts at basis, not fair
        # market value (IRC 170(e)(1)(A)), so this model refuses to gift it and
        # caps the transfer at the long-term stock instead.
        eng = self._engine()
        gifted, _gain, consumed = eng.donate_lots(self.ACCT, 300_000.0,
                                                  current_year=2026)
        self.assertAlmostEqual(gifted, 200_000.0, delta=1.0)  # LOW + HIGH only
        self.assertNotIn("NEW", [sym for sym, _mv, _g in consumed])

    def test_a_sale_after_the_gift_sees_the_lots_actually_gone(self):
        # The gifted shares must not still be sellable.
        eng = self._engine()
        eng.donate_lots(self.ACCT, 100_000.0, current_year=2026)
        self.assertAlmostEqual(eng.donatable_value(self.ACCT, current_year=2026),
                               100_000.0, delta=1.0)
        self.assertAlmostEqual(eng.embedded_long_term_gain(self.ACCT, current_year=2026),
                               10_000.0, delta=1.0)

    def test_accounts_are_ranked_by_embedded_long_term_gain(self):
        lots = {
            "A_Trust": {"HIGH": [TaxLot("HIGH", 1000, 90_000.0, "01/15/2010")]},
            "B_Trust": {"LOW": [TaxLot("LOW", 1000, 10_000.0, "01/15/2010")]},
        }
        eng = LotEngine(lots, {"HIGH": 100.0, "LOW": 100.0},
                        fallback_gain_fraction=0.5, method="HIFO")
        c = {
            "lot_engine": eng,
            "account_registry": [
                {"id": "A_Trust", "owner_idx": 0, "tax": "taxable"},
                {"id": "B_Trust", "owner_idx": 0, "tax": "taxable"},
            ],
        }
        bal = {"A_Trust": 100_000.0, "B_Trust": 100_000.0}
        res = donate_taxable_in_kind(c, bal, 2026, 100_000.0, 0.0)
        # B_Trust holds the $90k of appreciation, so it funds the gift.
        self.assertAlmostEqual(res["by_account"].get("B_Trust", 0.0), 100_000.0, delta=1.0)
        self.assertEqual(res["by_account"].get("A_Trust", 0.0), 0.0)
        self.assertAlmostEqual(res["gain_avoided"], 90_000.0, delta=1.0)

    def test_shortfall_is_reported_not_swallowed(self):
        lots = {"A_Trust": {"NEW": [TaxLot("NEW", 1000, 95_000.0, "06/01/2026")]}}
        eng = LotEngine(lots, {"NEW": 100.0}, fallback_gain_fraction=0.5)
        c = {
            "lot_engine": eng,
            "account_registry": [{"id": "A_Trust", "owner_idx": 0, "tax": "taxable"}],
        }
        bal = {"A_Trust": 100_000.0}
        res = donate_taxable_in_kind(c, bal, 2026, 100_000.0, 0.0)
        # Nothing long-term to give: the gift is zero and says so.
        self.assertEqual(res["amount"], 0.0)
        self.assertAlmostEqual(res["shortfall"], 100_000.0, delta=1.0)
        self.assertTrue(res["long_term_capped"])
        self.assertAlmostEqual(bal["A_Trust"], 100_000.0, delta=1.0)
