from __future__ import annotations

import importlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ModularizationTests(unittest.TestCase):
    def test_legacy_monolithic_source_files_are_removed(self):
        self.assertFalse((ROOT / 'src' / 'reporting.py').exists())
        self.assertFalse((ROOT / 'src' / 'server.py').exists())
        self.assertFalse((ROOT / 'src' / 'ui_builder.py').exists())

    def test_workbook_entrypoint_is_modular(self):
        mod = importlib.import_module('src.reporting.workbook_builder')
        self.assertTrue(callable(mod.main))
        self.assertTrue((ROOT / 'src' / 'reporting' / 'sheets_summary.py').exists())
        self.assertTrue((ROOT / 'src' / 'reporting' / 'dashboard.py').exists())

    def test_local_server_import_path_still_works_without_flask(self):
        from src.server import create_app
        app = create_app()
        self.assertIsNotNone(app)
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        self.assertIn('/api/ping', rules)
        self.assertIn('/api/build', rules)
        self.assertIn('/api/config/rows', rules)

    def test_dashboard_ui_builder_is_modular(self):
        mod = importlib.import_module('src.dashboard_ui.builder')
        self.assertTrue(callable(mod.write_dashboard_ui))

    def test_large_source_files_are_below_modular_threshold(self):
        # The prior monoliths were ~5,800 and ~2,350 lines. Keep replacement
        # modules small enough to be reviewable.
        max_lines = 3000
        offenders = []
        scoped_roots = [ROOT / 'src' / 'reporting', ROOT / 'src' / 'server', ROOT / 'src' / 'dashboard_ui']
        for base in scoped_roots:
            for path in base.rglob('*.py'):
                rel = path.relative_to(ROOT)
                if any(part == '__pycache__' for part in rel.parts):
                    continue
                count = len(path.read_text(encoding='utf-8').splitlines())
                if count > max_lines:
                    offenders.append((str(rel), count))
        self.assertFalse(offenders, offenders)


if __name__ == '__main__':
    unittest.main()
