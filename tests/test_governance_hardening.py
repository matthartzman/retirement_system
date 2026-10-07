from __future__ import annotations
import json, re, subprocess, sys, unittest
from pathlib import Path
from conftest import TEST_INPUT_DIR
ROOT=Path(__file__).resolve().parents[1]

class GovernanceHardeningTests(unittest.TestCase):
    def test_version_is_centralized_and_release_gate_detects_stale_surfaces(self):
        """Deliberately does not hardcode a specific version number (found
        2026-09-04, mid version bump: this test's original
        `self.assertEqual(VERSION, '11')`/`assertIn('v11', ...)` needed a
        manual edit on every single bump, exactly the hardcoding
        bump_version.py's own comprehensiveness audit was trying to purge
        elsewhere -- this test just wasn't in scope of that audit's file
        scan, since it's a fixed-string comparison, not a filename or
        display-text pattern). Checks the *shape* src/version.py's own
        bump() already enforces (a plain integer string) plus that
        RELEASE_LABEL is actually derived from VERSION, which is what this
        test exists to guard -- not which specific number it currently is."""
        from src.version import VERSION, RELEASE_LABEL
        self.assertRegex(VERSION, r'^\d+$')
        self.assertIn(f'v{VERSION}', RELEASE_LABEL)
        out=subprocess.run([sys.executable,'tools/check_version_surfaces.py'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(out.returncode,0,out.stdout+out.stderr)

    def test_admin_ui_is_split_into_modules(self):
        html=(ROOT/'frontend/admin.html').read_text(encoding='utf-8')
        self.assertIn('css/admin.css', html)
        self.assertIn('js/admin.js', html)
        self.assertNotIn('<style>', html)
        self.assertNotIn('<script>\nfunction', html)
        self.assertTrue((ROOT/'frontend/css/admin.css').exists())
        js=(ROOT/'frontend/js/admin.js').read_text(encoding='utf-8')
        self.assertIn('showTaxLawDashboard', js)
        self.assertIn('showAdvisorSignoff', js)

    def test_exact_scalar_mc_validation_mode_and_vectorized_labeling(self):
        from src.data_io import load_csv, parse_client
        from src.planning_engines import monte_carlo
        cfg=parse_client(load_csv(TEST_INPUT_DIR/'client_data.csv'), '')
        cfg['mc_sims']=8; cfg['mc_sensitivity_sims']=2; cfg['mc_use_asset_class_covariance']=False
        cfg['mc_engine_mode']='exact_scalar'
        exact=monte_carlo(dict(cfg), seed=812)
        self.assertEqual(exact.get('mc_engine'),'exact_scalar')
        cfg['mc_engine_mode']='vectorized'
        approx=monte_carlo(dict(cfg), seed=812)
        self.assertIn('vectorized', approx.get('mc_engine',''))
        self.assertEqual(approx.get('mc_approximation_status'), 'TOLERANCE_BOUNDED')
        self.assertGreaterEqual(approx['success_rate'],0.0)
        self.assertLessEqual(approx['success_rate'],1.0)

    def test_schema_coverage_exists(self):
        # WP4.5: the plan-data folder manifest and its sync check are gone with the CSV bridge.
        self.assertTrue((ROOT/'reference_src/generated_schema_coverage.csv').exists())

    def test_tax_governance_and_advisor_readiness_labels(self):
        from src.governance import tax_law_dashboard, advisor_readiness, model_risk_rating
        rows=tax_law_dashboard()
        self.assertTrue(any(r['constant']=='federal_brackets' for r in rows))
        mc={'portfolio_return_diagnostics':{'mc_engine':'vectorized_batched_tax_withdrawal'},'mc_approximation_status':'APPROXIMATE_PENDING_SCALAR_PARITY'}
        ready=advisor_readiness({'tax_table_currency_warnings':['stale'], 'spend_base':100000}, mc, {'sources':{'ABC':'fallback_cost_basis'}, 'prices':{'ABC':1}})
        self.assertEqual(ready['status'],'BLOCKED')
        self.assertEqual(model_risk_rating(mc)['rating'],'APPROXIMATE_VECTORIZED_MC')
if __name__=='__main__': unittest.main()
