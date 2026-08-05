from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AllocationUIBackfillTests(unittest.TestCase):
    def test_server_backfills_missing_allocation_rows_for_older_plan_data(self):
        source = (ROOT / 'src' / 'server' / 'app_core.py').read_text(encoding='utf-8')
        # A7 (Wave 3 item 3.12): the twelve near-identical
        # _ensure_*_ui_plan_data_rows functions (including allocation and HSA
        # withdrawal) were replaced by one declarative
        # PLAN_DATA_BACKFILL_ENTRIES table applied via
        # _ensure_user_ui_plan_data_rows() -> plan_data_backfill.apply_backfill().
        self.assertIn('_ensure_user_ui_plan_data_rows()', source)
        self.assertLess(source.index('_ensure_user_ui_plan_data_rows()'), source.index('schema = _read_schema_map()'))
        import src.server.app_core as ac
        assert any(entry.rows is ac.ALLOCATION_UI_PLAN_DATA_ROWS for entry in ac.PLAN_DATA_BACKFILL_ENTRIES)
        assert any(entry.rows is ac.HSA_WITHDRAWAL_UI_PLAN_DATA_ROWS for entry in ac.PLAN_DATA_BACKFILL_ENTRIES)
        self.assertIn('allocation_selection_mode', source)
        self.assertIn('optimizer_override_pct', source)
        self.assertIn('DEFAULT_ALLOCATION_TARGETS', source)
        self.assertIn('asset_class_optimizer_controls.csv', source)

    def test_allocation_mode_buttons_are_rendered_without_generic_empty_field_group(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('setAllocationSelectionMode', html)
        self.assertIn("setAllocationSelectionMode('user_target')", html)
        self.assertIn("setAllocationSelectionMode('optimizer_recommendation')", html)
        self.assertIn('Use user-specified allocation', html)
        self.assertIn('Use allocation optimizer recommendation', html)
        # The mode panel must not call renderFieldGroups(common), because when
        # the common rows are missing it was displaying "No fields in this step"
        # instead of the toggle.
        self.assertNotIn('renderFieldGroups(common)', html)

    def test_allocation_recommendation_has_actionable_missing_row_notes_not_empty_step(self):
        html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('targetPctInput', html)
        self.assertIn('Asset-class selection rows were not found', html)
        self.assertIn('asset_class_optimizer_controls.csv can be backfilled', html)
        block = re.search(r"function renderAllocationRecommendation\(\).*?return html\}", html, re.S)
        self.assertIsNotNone(block)
        self.assertNotIn('No fields in this step', block.group(0))


if __name__ == '__main__':
    unittest.main()
