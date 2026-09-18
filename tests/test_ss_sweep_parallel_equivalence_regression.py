"""The claim-age pair evaluator must be a picklable, module-level callable.

Windows spawns worker processes, so a closure (the shape this logic had
before) cannot cross the process boundary.
"""
from __future__ import annotations

import pickle
import unittest

from src.reporting.sheets_strategy_pair_worker import evaluate_claim_age_pair


class PairWorkerContract(unittest.TestCase):
    def test_worker_is_a_module_level_callable(self):
        self.assertTrue(callable(evaluate_claim_age_pair))
        self.assertEqual(
            evaluate_claim_age_pair.__module__,
            'src.reporting.sheets_strategy_pair_worker',
        )

    def test_worker_is_picklable(self):
        self.assertIs(pickle.loads(pickle.dumps(evaluate_claim_age_pair)),
                      evaluate_claim_age_pair)


if __name__ == '__main__':
    unittest.main()
