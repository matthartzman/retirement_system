import json
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client, summarize_validation
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.server_forecast import forecast_from_plan_json

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / 'input' / 'client_data.csv')
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
        # Golden-master constants are tied to input/client_data.csv (and its
        # transaction/budget-derived spend base) as of this commit. Regenerate
        # them deliberately after intentional plan-data changes; a mismatch
        # otherwise usually means a real projection-engine regression.
        #
        # Item 141 (2026-07): the projection spend_base dropped from 129,059 to
        # 124,059 after fixing a double-count in spending_budget_resolver — a
        # Core Expenses category (charitable giving) that carried BOTH a category
        # budget row and a detail line was counted twice. The 5,000/yr lower spend
        # reinvests as surplus, so terminal net worth and later-year taxes rise.
        #
        # Item 142 (2026-07-07 12:09 PM): spending budget line items updated manually
        # (dentist, medical, gifts, health club, vitamins) and miscellaneous/uncategorized
        # cleared out after taxonomy changes. Terminal net worth increased to ~12.4M.
        #
        # Item 143 (2026-07-08): one-time $40k family gift modeled as a
        # significant_gifts Large Discretionary line for 2026, plus an app re-sync of
        # client_spending_budget.csv (several category budgets adjusted, e.g.
        # entertainment/furniture/lawn lowered). This projection path does not apply
        # the current-year YTD blend, so the gift's effect here is just the $40k 2026
        # lump; net of the re-synced budgets, terminal net worth settles to ~11.32M
        # and lifetime tax to ~1.46M. Regenerate from a clean `git worktree` checkout
        # (no untracked local state) — a plain working-tree run can pick up gitignored
        # local caches (e.g. output/pricing_diagnostics.json, live holdings snapshots)
        # that inflate balances by $1M+ versus CI's committed-only checkout.
        #
        # Item 165 (2026-07-08): DAF (Donor Advised Fund) feature activated
        # (input/client_assets.csv `enabled` flipped FALSE->TRUE). DAF contributions
        # reduce taxable income/AGI which lowers lifetime tax and, combined with the
        # tax savings compounding as reinvested surplus, raises terminal net worth to
        # ~12.24M and lifetime tax to ~1.55M.
        #
        # Item 166 (2026-07-09): dividend reinvestment feature. Dividends/interest
        # no longer directly fund spending as "Portfolio Income" — they either
        # compound into the holding or convert to account-internal cash (Reinvest
        # Dividends toggle, per account and a global override; this sample plan's
        # client_household.csv has the global switch on). Removing that free cash
        # from the income funding calc means the withdrawal cascade sells more to
        # cover the same spending, realizing capital gains tax the old model
        # avoided. Terminal net worth drops to ~12.11M and lifetime tax to ~1.50M.
        #
        # Item 167 (2026-07-09): tax-loss harvesting feature (tlh_policy defaults
        # to off, so the engine change itself is a no-op) landed alongside plan-data
        # edits made through the running app during that work: annual_earned_income
        # raised to $309,620 (from $290,000), a Liquidity Buffer reserve activated
        # for 2027-2029, a $5,000 charitable-giving budget line removed, and Medicare
        # Part B/D/Medigap premiums rebalanced. Net effect: terminal net worth drops
        # to ~9.40M and lifetime tax to ~1.31M — a real plan-data change, not an
        # engine regression.
        #
        # Item 185 (2026-07-14): the elective pre-tax IRA/401(k) withdrawal used
        # to size itself off a flat federal-marginal-rate gross-up
        # (withdraw_pretax_elective's `gross_up`), which ignores state tax and
        # bracket integration, and its ordinary income was never added to
        # agi/taxable_inc. Added a bounded fixed-point true-up (mirroring the
        # existing LTCG/NIIT loop) that re-solves against the real progressive
        # fed+state tax and folds the withdrawal into agi/taxable_inc/irmaa_magi.
        # This is why some rows previously showed both an elective withdrawal and
        # a "reinvested surplus" in the cash-bridge sheet at the same time.
        # Also fixed a second, related bug the true-up exposed: `new_gap` was
        # reduced by a flat-rate-estimated `net_cash`, while required_portfolio_
        # draws (the cash-bridge sheet and this true-up) count the full gross
        # withdrawal — the two conventions double-booked/mis-booked the tax and
        # left the cash-bridge reconciliation off by the mismatch (confirmed via
        # `git stash` against the pre-Item-185 code — this reconciliation gap,
        # smaller but present, pre-dates this fix). `new_gap` now reduces by the
        # full gross amount, matching withdraw_taxable_trust's convention, so
        # the true-up's real tax delta is the only tax accounting in play.
        # Elective withdrawals end up smaller (correctly sized, not over-drawn),
        # letting more compound tax-deferred: terminal net worth rises to
        # ~7.32M and lifetime tax rises to ~1.62M.
        #
        # These constants are now fully reproducible: tests/conftest.py pins
        # holdings pricing to OFFLINE, so starting balances come from the
        # committed cache snapshot rather than live market data. Confirmed
        # identical across Python 3.12 and 3.14 on Windows (both interpreters
        # agree to the cent); regenerate deliberately after an intentional
        # engine/plan-data change.
        c = sample_config()
        rows = project(c)
        summary = summarize_validation(rows, c)
        self.assertEqual(summary['fail_count'], 0)
        self.assertEqual(summary['warn_count'], 0)
        self.assertEqual((rows[0]['year'], rows[-1]['year'], len(rows)), (2026, 2056, 31))
        # Baselines reflect the committed sample inputs plus two intentional
        # engine changes: item 182 (pre-65 bridge premium applies to any pre-65
        # person regardless of retirement year) and item 184 (real-estate tax is
        # funded as a cash need, not only used for the SALT deduction). Values
        # were regenerated against clean committed inputs — a fresh checkout / CI
        # reproduces them (holdings are pinned OFFLINE via tests/conftest.py).
        #
        # Item 168 (2026-07-14): `load_csv` merges every sibling client_*.csv
        # file, so this sample config picks up client_household.csv's real
        # per-age SS benefit tables even though client_data.csv itself has no
        # SS fields. Fixing the SS benefit self-cancellation bug (13b089a)
        # moved the claimed amount from a flat back-solved number to a real
        # per-age table lookup (a small change: ~$5,080/mo flat -> the real
        # age-70 figure), and separately fixed Social Security's present value
        # being silently excluded from the fixed-income coverage calculation
        # (ss_pv was always 0 before the fix). Together these ripple through
        # the withdrawal/tax cascade to shift terminal net worth by ~$33k.
        # Verified via `git worktree` bisection: the prior pin
        # (6,745,962.88 / 971,088.96) reproduces exactly at commit dcfe794, and
        # the intermediate value (6,712,722.02 / 965,325.67) reproduces exactly
        # at 13b089a, in a clean checkout free of gitignored local cache files
        # (which can inflate a plain working-tree run by $800k+ - see item 143).
        #
        # Item 169 (2026-07-14): household plan update - Social Security claim
        # age moved from 70 to 69 for both spouses (matching Sheet 10's
        # projection-sweep recommendation), and FRA Age set explicitly to 67
        # (same as the auto-derived default, no behavior change). Claiming one
        # year earlier changes which ss_benefit_age_* table entry is used and
        # shifts the whole withdrawal/tax cascade.
        #
        # Item 185 (2026-07-14): elective pre-tax IRA/401(k) withdrawal
        # ordinary-tax true-up + gap/net_cash convention fix (see
        # deterministic_engine.py's _ira_elective_ordinary_tax_delta) —
        # terminal net worth rises to ~7.32M, lifetime tax to ~1.62M.
        #
        # Item 186 (2026-07-14): household plan update - Member 1 Social
        # Security claim age moved from 69 to 68 (Member 2 unchanged at 69).
        # Terminal net worth rises to ~7.36M, lifetime tax to ~1.63M.
        #
        # The previously-noted order-dependency (this value shifting ~$800k
        # depending on whether test_forecast_api_service_uses_same_config_
        # contract ran first) was the same pricing-cache leak fixed by the
        # tests/conftest.py _reset_market_data_price_cache autouse fixture;
        # this value is now stable both in full-suite and isolated runs.
        self.assertAlmostEqual(rows[-1]['total_nw'], 7_357_655.92, delta=5000.0)
        self.assertAlmostEqual(sum(r['total_tax'] for r in rows), 1_630_920.02, delta=5000.0)

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
        # Verify Roth is not tapped when pre-tax/trust/HSA funds are available
        self.assertEqual(sum(
            1 for r in rows
            if r.get('roth_wd', 0) > 1 and (r.get('pretax_nw', 0) + r.get('trust_nw', 0) + r.get('hsa_nw', 0)) > 1
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
        plan = json.loads((ROOT / 'input' / 'client_data.json').read_text())
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
