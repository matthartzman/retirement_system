"""Tests for UI wiring of the holding-period real-loss allocation feature:

- src/server/app_core.py's ALLOCATION_UI_PLAN_DATA_ROWS backfill list
  (materializes editable Plan Data rows for holding_period_allocation_enabled,
  holding_period_floor_strength, real_loss_aware_risk_aversion,
  real_loss_aware_weight, and the capital-market horizon/preset/source group).
- frontend/js/dashboard.js: the real_loss_aware allocation mode in the mode
  dropdown/button panel, allocationSelectionMode()'s normalizer, the new
  renderRealLossAwarePanel() dispatch, and the gating/guidance logic for the
  new fields.

Mirrors tests/test_10_allocation_ui_backfill.py's and
tests/test_39_active_input_recursion_guard.py's conventions: string-presence
checks against the real backend list/frontend source, plus a node smoke test
that actually executes dashboard.js's functions (not just string-matches)
against a minimal DOM mock.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "frontend" / "js" / "dashboard.js"
JS_DIR = ROOT / "frontend" / "js"


def _dashboard_smoke_sources():
    """dashboard.js plus every extracted dashboard_decomp_*.js module, in the
    same load order as index.html (extracted modules before dashboard.js) so the
    node smoke harness exercises the real, fully-assembled behavior."""
    mods = sorted(JS_DIR.glob("dashboard_decomp_*.js"))
    return [str(m) for m in mods] + [str(JS)]


def _smoke_sources_js_array():
    return "[" + ", ".join(repr(s) for s in _dashboard_smoke_sources()) + "]"


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        return True
    except Exception:
        return False


class AllocationUIBackfillRowsTests(unittest.TestCase):
    def test_allocation_ui_plan_data_rows_include_new_fields(self):
        sys.path.insert(0, str(ROOT))
        from src.server.app_core import ALLOCATION_UI_PLAN_DATA_ROWS

        keys = {(row[0], row[1], row[2]) for row in ALLOCATION_UI_PLAN_DATA_ROWS}
        expected = {
            ("Asset Allocation Policy", "Global", "allocation_selection_mode"),
            ("Asset Allocation Policy", "Global", "holding_period_allocation_enabled"),
            ("Asset Allocation Policy", "Global", "holding_period_floor_strength"),
            ("Asset Allocation Policy", "Global", "real_loss_aware_risk_aversion"),
            ("Asset Allocation Policy", "Global", "real_loss_aware_weight"),
            ("Asset Class Assumptions", "Global", "capital_market_assumption_horizon_years"),
            ("Asset Class Assumptions", "Global", "capital_market_assumption_horizon_source"),
            ("Asset Class Assumptions", "Global", "capital_market_assumption_preset"),
        }
        self.assertTrue(expected.issubset(keys), keys)

    def test_allocation_selection_mode_default_row_still_user_target(self):
        sys.path.insert(0, str(ROOT))
        from src.server.app_core import ALLOCATION_UI_PLAN_DATA_ROWS

        row = next(
            r for r in ALLOCATION_UI_PLAN_DATA_ROWS
            if (r[0], r[1], r[2]) == ("Asset Allocation Policy", "Global", "allocation_selection_mode")
        )
        self.assertEqual(row[3], "user_target")
        self.assertIn("real_loss_aware", row[5])

    def test_new_boolean_and_decimal_rows_have_byte_stable_defaults(self):
        sys.path.insert(0, str(ROOT))
        from src.server.app_core import ALLOCATION_UI_PLAN_DATA_ROWS

        by_key = {(r[0], r[1], r[2]): r for r in ALLOCATION_UI_PLAN_DATA_ROWS}
        self.assertEqual(by_key[("Asset Allocation Policy", "Global", "holding_period_allocation_enabled")][3], "NO")
        self.assertEqual(by_key[("Asset Allocation Policy", "Global", "real_loss_aware_risk_aversion")][3], "3.0")
        self.assertEqual(by_key[("Asset Allocation Policy", "Global", "real_loss_aware_weight")][3], "1.0")
        self.assertEqual(
            by_key[("Asset Class Assumptions", "Global", "capital_market_assumption_horizon_source")][3], "manual"
        )


class DashboardJsStringPresenceTests(unittest.TestCase):
    def read_js(self):
        return JS.read_text(encoding="utf-8")

    def test_real_loss_aware_present_in_mode_dropdown_and_buttons(self):
        js = self.read_js()
        self.assertIn('{ value: "real_loss_aware", label: "Use holding-period real-loss-aware allocation" }', js)
        self.assertIn('<option value="real_loss_aware"', js)
        self.assertIn('["real_loss_aware", "Use holding-period real-loss-aware allocation"]', js)

    def test_allocation_selection_mode_normalizer_recognizes_real_loss_aware(self):
        js = self.read_js()
        self.assertIn('return "real_loss_aware";', js)

    def test_real_loss_aware_panel_defined_and_dispatched(self):
        js = self.read_js()
        self.assertIn("function renderRealLossAwarePanel()", js)
        self.assertIn('else if (mode === "real_loss_aware") html += renderRealLossAwarePanel();', js)

    def test_new_fields_visible_on_allocation_assets_step(self):
        js = self.read_js()
        self.assertIn('"holding_period_allocation_enabled"', js)
        self.assertIn('"holding_period_floor_strength"', js)
        self.assertIn('"real_loss_aware_risk_aversion"', js)
        self.assertIn('"real_loss_aware_weight"', js)

    def test_gating_logic_present_for_floor_strength_and_real_loss_knobs(self):
        js = self.read_js()
        self.assertIn('l === "holding_period_floor_strength"', js)
        self.assertIn(
            'l === "real_loss_aware_risk_aversion" || l === "real_loss_aware_weight"', js
        )


@unittest.skipUnless(_node_available(), "node is not available in this environment")
class DashboardJsRuntimeBehaviorTests(unittest.TestCase):
    """Actually executes dashboard.js functions (not just string-matching)
    against a minimal DOM mock, mirroring
    test_39_active_input_recursion_guard.py's convention."""

    def _run_smoke(self, tmp_path: Path, script_body: str) -> str:
        script = tmp_path / "dashboard_real_loss_aware_smoke.js"
        harness = textwrap.dedent(f"""
            const fs = require('fs');
            const code = {_smoke_sources_js_array()}.map(f => fs.readFileSync(f, 'utf8')).join('\\n');
            const el = () => ({{
              style: {{}}, innerHTML: '', textContent: '', value: '', disabled: false,
              classList: {{ toggle(){{}}, remove(){{}}, add(){{}}, contains(){{return false;}} }},
              setAttribute(){{}}, addEventListener(){{}}, focus(){{}}, select(){{}}, click(){{}}
            }});
            global.window = {{
              sessionStorage: {{ getItem(){{return null;}}, setItem(){{}}, removeItem(){{}} }},
              localStorage: {{ getItem(){{return null;}}, setItem(){{}} }},
              open(){{}}, addEventListener(){{}}, location: {{ href: '' }}
            }};
            global.document = {{
              getElementById(){{return el();}}, querySelector(){{return el();}}, querySelectorAll(){{return [];}}, addEventListener(){{}},
              body: {{ classList: {{ toggle(){{}}, remove(){{}}, add(){{}} }} }}
            }};
            global.fetch = async () => ({{ ok: true, text: async () => '', json: async () => ({{success:true, rows:[]}}) }});
            global.setInterval = () => 0; global.clearInterval = () => {{}};
            global.setTimeout = () => 0; global.clearTimeout = () => {{}};
            const smoke = `
              {script_body}
            `;
            eval(code + '\\n' + smoke);
        """)
        script.write_text(harness, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script)], cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.fail(f"node smoke script failed:\n{result.stdout}\n{result.stderr}")
        return result.stdout

    def test_allocation_selection_mode_recognizes_real_loss_aware_value(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'}
              ];
              const mode = allocationSelectionMode();
              if (mode !== 'real_loss_aware') { throw new Error('expected real_loss_aware, got ' + mode); }
              console.log('OK:' + mode);
            """)
            self.assertIn("OK:real_loss_aware", out)

    def test_allocation_mode_html_renders_real_loss_aware_button(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'}
              ];
              const html = allocationModeHtml();
              if (!html.includes('Use holding-period real-loss-aware allocation')) {
                throw new Error('missing real_loss_aware button label');
              }
              if (!html.includes('primary')) { throw new Error('active button not marked primary'); }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_holding_period_floor_strength_inactive_when_toggle_off(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_allocation_enabled',value:'NO'},
                {row_index:2,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_floor_strength',value:'100%'}
              ];
              const state = rowBuildUsageState(rows[1], 'allocation_assets');
              if (state.active !== false) { throw new Error('expected inactive, got ' + JSON.stringify(state)); }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_holding_period_floor_strength_active_when_toggle_on(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_allocation_enabled',value:'YES'},
                {row_index:2,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_floor_strength',value:'100%'}
              ];
              const state = rowBuildUsageState(rows[1], 'allocation_assets');
              if (state.active !== true) { throw new Error('expected active, got ' + JSON.stringify(state)); }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_real_loss_aware_weight_inactive_unless_mode_selected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'user_target'},
                {row_index:2,section:'Asset Allocation Policy',subsection:'Global',label:'real_loss_aware_weight',value:'1.0'}
              ];
              const state = rowBuildUsageState(rows[1], 'allocation_assets');
              if (state.active !== false) { throw new Error('expected inactive, got ' + JSON.stringify(state)); }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_render_real_loss_aware_panel_does_not_throw(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'}
              ];
              allocationPreview = {
                selected_diagnostics: {
                  real_loss_aware_bucket_shares: { '0-2 yr': 0.4, '16+ yr': 0.6 }
                }
              };
              const html = renderRealLossAwarePanel();
              if (!html.includes('real-loss-aware')) { throw new Error('missing title text'); }
              if (!html.includes('0-2 yr')) { throw new Error('missing bucket row'); }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_asset_class_selection_note_reflects_real_loss_aware_mode(self):
        # Regression guard: renderAssetClassSelectionTable() has its own
        # separate mode dispatch (distinct from renderAllocationRecommendation's)
        # for the descriptive note above the asset-class table. Before this
        # fix it had no real_loss_aware branch and silently fell through to
        # the "User-defined mode is active" text meant for user_target.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'},
                {row_index:2,section:'Asset Class Optimizer Controls',subsection:'US Large Cap',label:'selection_action',value:'include'}
              ];
              const html = renderAssetClassSelectionTable();
              if (!html.includes('Holding-period real-loss-aware mode is active')) {
                throw new Error('missing real_loss_aware note: ' + html.slice(0, 400));
              }
              if (html.includes('User-defined mode is active')) {
                throw new Error('stale user_target note leaked into real_loss_aware mode');
              }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_request_allocation_preview_fires_on_distribution_strategy_step(self):
        # Regression guard: requestAllocationPreview() originally only
        # fired when activeStep === "allocation_assets", a legacy standalone
        # step id. The current guided-steps UI hosts Allocation & Location
        # inside the combined "distribution_strategy" step, so the preview
        # (and therefore the real_loss_aware bucket table) never loaded
        # without this fix. Checks the synchronous portion of
        # requestAllocationPreview (allocationPreviewLoading flips to true
        # before the guard would have returned early) rather than mocking
        # fetch/api's async chain, which is more robust to that layer's
        # internal timing.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'}
              ];
              planLoaded = true;
              activeStep = 'distribution_strategy';
              requestAllocationPreview();
              if (allocationPreviewLoading !== true) {
                throw new Error('requestAllocationPreview returned early on distribution_strategy step (guard not updated)');
              }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_holding_period_settings_and_tuning_blocks_render_fields(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'},
                {row_index:2,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_allocation_enabled',value:'NO'},
                {row_index:3,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_floor_strength',value:'100%'},
                {row_index:4,section:'Asset Allocation Policy',subsection:'Global',label:'real_loss_aware_risk_aversion',value:'3.0'},
                {row_index:5,section:'Asset Allocation Policy',subsection:'Global',label:'real_loss_aware_weight',value:'1.0'}
              ];
              const settingsHtml = renderHoldingPeriodSettingsHtml();
              const tuningHtml = renderRealLossAwareTuningHtml();
              if (!settingsHtml.includes('Holding-period allocation settings')) {
                throw new Error('settings block missing heading: ' + settingsHtml.slice(0, 300));
              }
              if (!tuningHtml.includes('Real-loss-aware tuning')) {
                throw new Error('tuning block missing heading: ' + tuningHtml.slice(0, 300));
              }
              console.log('OK');
            """)
            self.assertIn("OK", out)

    def test_dashboard_js_recursion_guard_smoke_still_passes_with_new_fields(self):
        # Extends the existing recursion-guard smoke test with the new rows
        # to confirm rowBuildUsageState's new branches don't introduce
        # infinite recursion or crashes when mixed with existing fields.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = self._run_smoke(Path(td), """
              rows = [
                {row_index:1,section:'Asset Allocation Policy',subsection:'Global',label:'allocation_selection_mode',value:'real_loss_aware'},
                {row_index:2,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_allocation_enabled',value:'YES'},
                {row_index:3,section:'Asset Allocation Policy',subsection:'Global',label:'holding_period_floor_strength',value:'100%'},
                {row_index:4,section:'Asset Allocation Policy',subsection:'Global',label:'real_loss_aware_risk_aversion',value:'3.0'},
                {row_index:5,section:'Asset Allocation Policy',subsection:'Global',label:'real_loss_aware_weight',value:'1.0'}
              ];
              rows.map(r => rowBuildUsageState(r, 'allocation_assets'));
              console.log('OK');
            """)
            self.assertIn("OK", out)


if __name__ == '__main__':
    unittest.main()
