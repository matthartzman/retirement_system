"""spend_as_needed used to cap the HSA draw at that year's wellness cost. With a
substantiated expense bank, the cap is the bank, not the calendar."""
import unittest
from src.planning_engines import hsa_available_to_draw, withdraw_hsa_window

C = {"hsa_ids": ["Member_1_HSA"], "hsa_withdrawal_mode": "spend_as_needed",
     "hsa_expense_bank": None}


class HsaDecouplingTests(unittest.TestCase):
    def test_unlimited_bank_allows_a_draw_beyond_this_years_medical_cost(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C), bal, 2030, wellness_cost=5_000.0, requested=40_000.0)
        self.assertAlmostEqual(out["amount"], 40_000.0, places=6)

    def test_a_finite_bank_caps_the_draw(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C, hsa_expense_bank=12_000.0), bal, 2030,
                                  wellness_cost=5_000.0, requested=40_000.0)
        self.assertAlmostEqual(out["amount"], 12_000.0, places=6)

    def test_no_requested_amount_preserves_the_old_wellness_behavior(self):
        """Backward compatibility: existing plans pass no `requested` and must be
        bit-identical to today."""
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C), bal, 2030, wellness_cost=5_000.0)
        self.assertAlmostEqual(out["amount"], 5_000.0, places=6)


class HsaAvailableToDrawTests(unittest.TestCase):
    """The helper the later optimizer tasks consume."""

    def test_none_bank_is_unlimited_and_returns_the_whole_balance(self):
        self.assertAlmostEqual(
            hsa_available_to_draw(dict(C), {"Member_1_HSA": 100_000.0}), 100_000.0, places=6)

    def test_a_zero_bank_is_not_unlimited(self):
        """0.0 means no substantiated receipts at all -- the opposite of None."""
        self.assertAlmostEqual(
            hsa_available_to_draw(dict(C, hsa_expense_bank=0.0),
                                  {"Member_1_HSA": 100_000.0}), 0.0, places=6)

    def test_cumulative_draws_consume_the_bank(self):
        self.assertAlmostEqual(
            hsa_available_to_draw(dict(C, hsa_expense_bank=30_000.0),
                                  {"Member_1_HSA": 100_000.0}, 25_000.0), 5_000.0, places=6)

    def test_an_exhausted_bank_never_goes_negative(self):
        self.assertAlmostEqual(
            hsa_available_to_draw(dict(C, hsa_expense_bank=30_000.0),
                                  {"Member_1_HSA": 100_000.0}, 45_000.0), 0.0, places=6)

    def test_the_balance_still_binds_below_a_generous_bank(self):
        self.assertAlmostEqual(
            hsa_available_to_draw(dict(C, hsa_expense_bank=500_000.0),
                                  {"Member_1_HSA": 100_000.0}), 100_000.0, places=6)


class ExistingModesAreUnchangedTests(unittest.TestCase):
    """annual_pct and smooth_window must be untouched by the decoupling, including
    when a bank is configured -- the bank bounds the spend_as_needed draw only."""

    def _windowed(self, mode: str) -> dict:
        return {"hsa_ids": ["Member_1_HSA"], "hsa_withdrawal_mode": mode,
                "hsa_win_start": 2030, "hsa_win_end": 2034,
                "hsa_annual_spend_pct": 0.10}

    def test_annual_pct_draws_its_percentage_regardless_of_bank_or_requested(self):
        for cfg in (self._windowed("annual_pct"),
                    dict(self._windowed("annual_pct"), hsa_expense_bank=1_000.0)):
            bal = {"Member_1_HSA": 100_000.0}
            out = withdraw_hsa_window(cfg, bal, 2030, wellness_cost=5_000.0, requested=40_000.0)
            self.assertAlmostEqual(out["amount"], 10_000.0, places=6)
            self.assertAlmostEqual(bal["Member_1_HSA"], 90_000.0, places=6)

    def test_smooth_window_spreads_over_the_window_regardless_of_bank(self):
        for cfg in (self._windowed("smooth_window"),
                    dict(self._windowed("smooth_window"), hsa_expense_bank=1_000.0)):
            bal = {"Member_1_HSA": 100_000.0}
            out = withdraw_hsa_window(cfg, bal, 2030, wellness_cost=5_000.0, requested=40_000.0)
            self.assertAlmostEqual(out["amount"], 20_000.0, places=6)  # 100k / 5 years

    def test_smooth_window_outside_the_window_draws_nothing(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(self._windowed("smooth_window"), bal, 2029,
                                  wellness_cost=5_000.0, requested=40_000.0)
        self.assertAlmostEqual(out["amount"], 0.0, places=6)

    def test_spend_as_needed_with_no_wellness_and_no_request_draws_nothing(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C), bal, 2030, wellness_cost=0.0)
        self.assertAlmostEqual(out["amount"], 0.0, places=6)
        self.assertAlmostEqual(bal["Member_1_HSA"], 100_000.0, places=6)


class ReserveFloorStillBindsTests(unittest.TestCase):
    """A reserve configured against the HSA bucket must not be drained by the new
    general-purpose draw -- otherwise the floor honored in withdraw_hsa_gap is
    moot because withdraw_hsa_window already emptied the account."""

    SPEND = 100_000.0

    def _plan(self) -> dict:
        return {
            "plan_start": 2026,
            "hsa_ids": ["Member_1_HSA"],
            "hsa_withdrawal_mode": "spend_as_needed",
            "hsa_expense_bank": None,
            "liquidity_buffer_schedule": [{
                "start_year": 2026, "end_year": 2035,
                "years_of_expenses": 2.0, "reserve_account": "HSA",
            }],
        }

    def test_a_requested_draw_stops_at_the_hsa_reserve_floor(self):
        bal = {"Member_1_HSA": 500_000.0}
        out = withdraw_hsa_window(self._plan(), bal, 2030, wellness_cost=5_000.0,
                                  requested=1_000_000.0, spend_floor_base=self.SPEND)
        self.assertAlmostEqual(out["amount"], 300_000.0, places=6)  # 500k - 2 * 100k
        self.assertAlmostEqual(bal["Member_1_HSA"], 200_000.0, places=6)

    def test_a_reserve_against_another_bucket_does_not_bind_the_hsa(self):
        plan = self._plan()
        plan["liquidity_buffer_schedule"][0]["reserve_account"] = "Roth"
        bal = {"Member_1_HSA": 500_000.0}
        out = withdraw_hsa_window(plan, bal, 2030, wellness_cost=5_000.0,
                                  requested=1_000_000.0, spend_floor_base=self.SPEND)
        self.assertAlmostEqual(out["amount"], 500_000.0, places=6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
