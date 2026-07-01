from __future__ import annotations
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.version import VERSION

class PricingUiReleaseTests(unittest.TestCase):
    def test_cache_any_age_precedes_cost_basis_in_cache_mode(self):
        from src.market_data import MarketDataProvider
        p = MarketDataProvider(cache_path=ROOT/'output'/'test_price_cache.json', diagnostics_path=ROOT/'output'/'test_pricing_diag.json', ttl_seconds=1)
        p.configure_holdings_pricing('CACHE', cache_hours=1)
        p.cache = {'ABC': {'price': 123.45, 'source': 'unit_test', 'timestamp_epoch': time.time() - 999999, 'timestamp_iso': '2000-01-01T00:00:00+00:00'}}
        p.set_fallback_prices({'ABC': 10.00})
        self.assertEqual(p.quote('ABC'), 123.45)
        self.assertIn('stale_cache', p.sources['ABC'])
        self.assertNotIn('cost_basis', p.sources['ABC'])

    def test_cost_basis_used_only_when_cache_missing(self):
        from src.market_data import MarketDataProvider
        p = MarketDataProvider(cache_path=ROOT/'output'/'test_missing_cache.json', diagnostics_path=ROOT/'output'/'test_missing_diag.json')
        p.configure_holdings_pricing('OFFLINE', cache_hours=1)
        p.cache = {}
        p.set_fallback_prices({'XYZ': 44.0})
        self.assertEqual(p.quote('XYZ'), 44.0)
        self.assertEqual(p.sources['XYZ'], 'holdings_cost_basis_fallback')

    def test_admin_and_user_help_panels_are_purpose_impact_consider_not_boilerplate(self):
        admin = (ROOT/'frontend/js/admin.js').read_text(encoding='utf-8')
        user = (ROOT/'frontend/js/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('What this page controls', admin)
        self.assertIn('Value options and how to choose', admin)
        self.assertIn('Likely planning or system impact', admin)
        self.assertNotIn('Keyboard behavior', admin)
        self.assertNotIn('Input model</h3>', admin)
        self.assertIn('Cost basis is now only a fallback when no cached quote exists', admin)
        self.assertIn('Cost basis is now a last-resort estimate only when there is no cached quote', user)

    def test_visible_release_surfaces_are_current(self):
        for rel in ['frontend/index.html','frontend/admin.html','system_config.csv','src/version.py']:
            text = (ROOT/rel).read_text(encoding='utf-8', errors='ignore')
            self.assertNotIn('Retirement System v8.1', text)
            if rel.endswith('system_config.csv'):
                self.assertIn(f'system_version,{VERSION}', text)
        out = __import__('subprocess').run([__import__('sys').executable, 'tools/check_version_surfaces.py'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

if __name__ == '__main__':
    unittest.main()
