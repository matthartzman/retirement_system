import json
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client, summarize_validation
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.server_forecast import forecast_from_plan_json
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]

from conftest import TEST_INPUT_DIR


def sample_config():
    data = load_csv(TEST_INPUT_DIR / 'client_data.csv')
    c = parse_client(data, '')
    c['roth_policy'] = 'none'
    c['mc_paths'] = 5
    c['mc_sensitivity_sims'] = 1
    return ensure_engine_config(c, source='test')



class RecommendationCompletionTests(unittest.TestCase):
    def test_config_contract_and_schema_source_are_recorded(self):
        c = sample_config()
        self.assertEqual(c['config_contract_version'], 'v1')
        self.assertIn(c['config_contract_source'], {'test', 'project', 'sectioned'})
        self.assertGreater(sum(c['balances'].values()), 0)
        self.assertTrue(c['all_acct_ids'])

    def test_sample_projection_golden_master_and_release_gate(self):
        # Structural gate for the frozen sample plan: no validation
        # failures/warnings, and the full 2026-2056 horizon.
        #
        # The two dollar figures this test used to carry (terminal_total_nw and
        # lifetime_tax) were REMOVED rather than re-pinned, 2026-08-12. They were
        # a second copy of
        # test_frozen_sample_plan_golden_master_regression.py's
        # PINNED_TERMINAL_NW / PINNED_LIFETIME_TAX -- same frozen fixture, same
        # frozen prices, same project() call, same two numbers -- and that
        # duplication is exactly what let a stale pin survive unnoticed.
        #
        # Both copies held 5,824,239.30 / 1,290,848.91, which the fixture has
        # never produced. The 2026-08-10 changelog entry corrected the
        # authoritative pair to the real values (6,044,750.40 / 1,465,666.69)
        # and this copy was missed, so it went on warning about a
        # +220,511 / +174,818 "drift" that did not exist. Verified before
        # deleting: the figures are byte-identical at f454117, 56c457a (the
        # commit that wrote the pins), e8eeb2e, ff8350d, 91ab5fe and main, and
        # across three consecutive runs -- i.e. unchanged straight through the
        # DAF-optimizer, per-account-draw-order and withdrawal-comparison
        # engine work. Nothing drifted; the pin was simply wrong.
        #
        # The old warn-only rationale ("these move whenever the sample client's
        # data is edited, which is routine") no longer held either: conftest
        # stages input/ from the committed tests/fixtures/sample_plan_frozen/
        # and pins the clock via RETIREMENT_SYSTEM_FROZEN_TODAY, so this plan is
        # static. Any real move in these dollars is an ENGINE change, and it now
        # fails test_frozen_sample_plan_golden_master_regression.py to the cent
        # instead of emitting a warning nobody reads. That file's __main__ regen
        # block is the single place to update. See
        # documentation/GOLDEN_MASTER_CHANGELOG.md.
        with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
            c = sample_config()
            rows = project(c)
        summary = summarize_validation(rows, c)
        self.assertEqual(summary['fail_count'], 0)
        self.assertEqual(summary['warn_count'], 0)
        self.assertEqual((rows[0]['year'], rows[-1]['year'], len(rows)), (2026, 2056, 31))

    def test_fixed_point_taxable_withdrawal_solver_runs_before_roth(self):
        # The fixed-point solver only runs when there's sufficient investment tax
        # (LTCG/NIIT) to fund via additional taxable withdrawals. With reduced
        # spending, we increase withdrawal pressure to trigger this behavior.
        c = sample_config()
        c['tax_withdrawal_fixed_point_iterations'] = 3
        # Elevate spending enough to create LTCG/NIIT that the fixed-point solver
        # must fund via taxable withdrawals, but not so much the plan draws Roth
        # once the trust reaches its protected reserve floor. Calibrated to 1.25x
        # against the committed sample net worth (1.20x-1.32x all trigger the
        # solver with zero Roth-ordering violations, verified under full-suite
        # execution order per the note on test_sample_projection_golden_master_and_release_gate);
        # outside that band the solver either doesn't trigger or depletes into
        # the reserve floor and forces Roth withdrawals. Item 169 (2026-07-14):
        # recalibrated after the household's Social Security claim age moved
        # 70->69, which shifted the safe-multiplier band to 1.15x-1.25x. Item 185
        # (2026-07-14): recalibrated again after the elective-IRA-withdrawal
        # ordinary-tax true-up fix (see deterministic_engine.py's
        # _ira_elective_ordinary_tax_delta) — withdraw_pretax_elective's
        # `new_gap` also changed from a flat-rate-net_cash haircut to the full
        # gross amount (matching withdraw_taxable_trust's convention), since
        # the true-up's real tax delta and the old net_cash haircut were
        # double-booking the tax and leaving the cash-bridge reconciliation off
        # by the mismatch. Elective IRA withdrawals are now smaller (correctly
        # sized against real tax instead of over-drawing), which shifted the
        # safe band to 1.20x-1.32x.
        c['spend_base'] = float(c.get('spend_base', 0)) * 1.25
        rows = project(c)
        # Verify the solver ran: higher spending creates LTCG/NIIT that needs funding
        total_iters = sum(r.get('investment_tax_iterations', 0) for r in rows)
        total_funded = sum(r.get('investment_tax_funded_by_taxable', 0) for r in rows)
        self.assertGreater(total_iters, 0, msg="Fixed-point solver should run with elevated spending")
        self.assertGreater(total_funded, 0, msg="Solver should fund investment taxes via taxable withdrawals")
        # Roth must not be tapped while genuinely LIQUID retirement funds remain.
        # The trust is intentionally excluded: it carries a protected reserve
        # floor the plan legitimately hits under the current (post-b246d19) income
        # assumptions, at which point tapping Roth is correct — not an ordering
        # bug. (Diagnostic 2026-07-17: with trust included, all violations across
        # every spend multiplier had pretax_nw==0 and hsa_nw==0, i.e. only the
        # protected trust reserve remained.) This still guards the real invariant:
        # Roth is never drawn ahead of available pre-tax/HSA balances.
        self.assertEqual(sum(
            1 for r in rows
            if r.get('roth_wd', 0) > 1 and (r.get('pretax_nw', 0) + r.get('hsa_nw', 0)) > 1
        ), 0)

    def test_ira_elective_withdrawal_tax_true_up(self):
        # Item 185: withdraw_pretax_elective sizes its gross-up off a flat
        # federal-marginal-rate estimate that ignores state tax and bracket
        # integration. Without a true-up, that mismatch shows up downstream as
        # a "reinvested surplus" in the cash-bridge sheet even in years with a
        # large elective withdrawal (see sheets_projection_cashflow.py's
        # Req_Portfolio_Draws/Cash_Bridge_Gap columns). The committed sample
        # plan runs a multi-decade pre-RMD bracket-fill elective IRA drawdown,
        # so roth_policy='none' (no competing Roth conversion strategy) is
        # enough to exercise this without any spend-multiplier tuning.
        c = sample_config()
        rows = project(c)

        total_true_up_iters = sum(r.get('ira_tax_true_up_iterations', 0) for r in rows)
        self.assertGreater(total_true_up_iters, 0,
                            msg="True-up loop should run at least once across the plan")

        elective_rows = [r for r in rows if r.get('ira_wd', 0) > 1]
        self.assertTrue(elective_rows, msg="Sample plan should have elective IRA withdrawal years")

        for r in elective_rows:
            with self.subTest(year=r['year']):
                required_portfolio_draws = (
                    r.get('h_trust_wd', 0) + r.get('w_trust_wd', 0) + r.get('hsa_wd', 0) +
                    r.get('h_roth_wd', 0) + r.get('w_roth_wd', 0) +
                    r.get('h_ira_elective', 0) + r.get('w_ira_elective', 0)
                )
                cash_bridge_gap = (
                    r['total_cash_need'] - r['income_funding'] - r.get('heloc_draw', 0) -
                    required_portfolio_draws
                )
                # Cash-bridge reconciliation identity (matches
                # sheets_projection_cashflow.py): Income Funding + Other Funding +
                # Required Portfolio Draws + Cash Bridge Gap == Total Cash Need.
                self.assertAlmostEqual(
                    r['income_funding'] + r.get('heloc_draw', 0) + required_portfolio_draws + cash_bridge_gap,
                    r['total_cash_need'], places=2,
                )
                # The true-up should leave at most a small residual "surplus" in a
                # year that also drew a real elective withdrawal — previously this
                # could be large (thousands to tens of thousands of dollars)
                # because the gross-up's flat-rate tax estimate went untrued.
                reinvested_surplus = max(0.0, -cash_bridge_gap)
                self.assertLess(reinvested_surplus, 25.0,
                                 msg=f"Reinvested surplus should be near zero alongside an elective withdrawal in {r['year']}")

    def test_tax_table_currency_warnings_surface_to_config(self):
        c = sample_config()
        warnings = c.get('tax_table_currency_warnings', [])
        self.assertFalse(any('federal_brackets' in w for w in warnings))
        self.assertEqual(warnings, [])

    def test_forecast_api_service_uses_same_config_contract(self):
        plan = json.loads((TEST_INPUT_DIR / 'client_data.json').read_text())
        result = forecast_from_plan_json(plan, run_mc=False)
        self.assertEqual(result['status'], 'ok')
        self.assertGreater(result['terminal_nw'], 0)
        self.assertEqual(result['validation']['fail_count'], 0)
        self.assertIn('config_contract_source', result)

    def test_duplicate_frontend_compatibility_file_removed(self):
        canonical = ROOT / 'frontend' / 'index.html'
        self.assertTrue(canonical.exists())
        self.assertEqual(len(list((ROOT / 'frontend').glob('*.html'))), 2)


if __name__ == '__main__':
    unittest.main()
