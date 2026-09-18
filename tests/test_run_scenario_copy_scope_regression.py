"""run_scenario must not mutate its caller's config, and must not waste time
deep-copying derived result blobs that no projection stage reads.
"""
from __future__ import annotations

import unittest

from src.planning_engines import _SCENARIO_IRRELEVANT_KEYS, run_scenario


class ScenarioCopyScope(unittest.TestCase):
    def test_result_blobs_are_declared_irrelevant(self):
        self.assertIn('plan_result', _SCENARIO_IRRELEVANT_KEYS)
        self.assertIn('report_spec', _SCENARIO_IRRELEVANT_KEYS)

    def test_caller_config_is_never_mutated(self):
        def fake_project(c2):
            c2['spend_base'] = 999999.0
            c2.setdefault('nested', {})['touched'] = True
            return []

        import src.planning_engines as pe
        original = pe.project
        pe.project = fake_project
        try:
            base = {
                'spend_base': 100.0,
                'nested': {'touched': False},
                'plan_result': {'big': [1, 2, 3]},
            }
            run_scenario(base, overrides={'spend_base': 200.0})
        finally:
            pe.project = original

        self.assertEqual(base['spend_base'], 100.0)
        self.assertFalse(base['nested']['touched'], "scenario mutated the caller's nested dict")


if __name__ == '__main__':
    unittest.main()
