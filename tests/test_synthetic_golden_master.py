"""Mandatory golden-master gate, driven entirely by synthetic plans.

This replaces the plan-coupled golden master in
``tests/test_phase5_validation_maturity.py`` as the *gating* engine baseline.
That one loaded ``input/client_data.csv`` (and, via ``load_csv``'s sibling
merge, every other ``input/client_*.csv``), so an edit to the advisor's real
plan data moved the pinned totals and failed CI — indistinguishable from an
actual engine regression.

Every plan exercised here is built in code (see ``tests/synthetic_plans.py``)
and reads nothing from ``input/``. Two tests below assert that property
mechanically rather than by convention.

CI wiring: no workflow change is needed. ``.github/workflows/ci.yml`` runs
``pytest tests/`` and ``tools/release_gate.py`` runs
``unittest discover -s tests``; both collect ``tests/test_*.py``, so this module
gates a merge and a release by the repo's existing convention.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

# Belt-and-braces alongside tests/conftest.py's OFFLINE pin: no test in this
# module may reach a live price provider, or the pinned dollars stop being
# reproducible.
os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.platform_runtime import WORKSPACE_SUBDIRS
from tests.golden_pricing import frozen_holdings_prices
from tests import synthetic_plans
from tests.synthetic_plans import SCENARIOS, project_metrics

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_golden_master_cases.json"


@contextlib.contextmanager
def empty_workspace():
    """Point the app's writable workspace at a tree containing no client files.

    tests/conftest.py redirects the workspace to a *copy* of the real ``input/``
    so the suite can't overwrite it. That is the right default, but it means a
    test cannot tell whether it is reading client data. Here the workspace is
    empty, so any accidental client-data read returns nothing and the scenario
    would fail loudly instead of silently picking the advisor's plan back up.
    """
    saved = os.environ.get("RETIREMENT_SYSTEM_WORKSPACE_ROOT")
    with tempfile.TemporaryDirectory(prefix="synthetic_golden_master_") as tmp:
        for name in WORKSPACE_SUBDIRS:
            (Path(tmp) / name).mkdir(parents=True, exist_ok=True)
        os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = tmp
        try:
            yield Path(tmp)
        finally:
            if saved is None:
                os.environ.pop("RETIREMENT_SYSTEM_WORKSPACE_ROOT", None)
            else:
                os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = saved


class SyntheticLibraryIsolationTests(unittest.TestCase):
    """Guards that keep the library from silently re-coupling to client data."""

    def test_library_source_contains_no_path_into_input(self):
        """Scan the library's executable tokens for anything that reaches input/.

        Comments and docstrings are excluded on purpose: the module explains at
        length *why* it avoids ``input/``, and that prose must not trip the
        guard. What matters is that no identifier or string literal the
        interpreter actually evaluates names client plan data.
        """
        import ast
        import io
        import tokenize

        source = Path(synthetic_plans.__file__).read_text(encoding="utf-8")

        # Line ranges occupied by docstrings, which are prose, not behavior.
        docstring_lines: set[int] = set()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc = body[0].value
                docstring_lines.update(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))

        code_tokens = []
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE):
                continue
            if tok.start[0] in docstring_lines:
                continue
            code_tokens.append((tok.start[0], tok.string))

        # Everything that would reach the advisor's plan data: the directory
        # itself, the client files, the loaders that resolve into it, and the
        # sectioned-CSV parser that hardcodes the repo-root holdings lookup.
        forbidden = [
            r"^input$", r"client_data", r"client_holdings", r"client_household",
            r"client_policy", r"client_optional_functions",
            r"^load_csv$", r"^parse_client$",
            r"^prepare_config_from_sectioned_data$", r"^load_active_config$",
            r"^load_engine_config$", r"^latest_sectioned_data$",
        ]
        for pattern in forbidden:
            hits = [f"line {lineno}: {text}" for lineno, text in code_tokens
                    if re.search(pattern, text)]
            self.assertEqual(
                hits, [],
                f"tests/synthetic_plans.py references {pattern!r}, which can reach "
                f"client plan data:\n" + "\n".join(hits),
            )

    def test_plans_do_not_route_into_the_sectioned_csv_parser(self):
        """``build_plan_from_json`` delegates to ``parse_client`` for sectioned input.

        ``parse_client`` resolves ``client_holdings.csv`` against the repo root
        (not the redirectable workspace), so a plan that trips the
        sectioned-data heuristic would silently read the advisor's real holdings
        and re-couple this gate to plan data. Assert every scenario stays on the
        flat-wizard branch.
        """
        from src.data_io import build_plan_from_json  # noqa: F401  (documents the path)
        import inspect

        source = inspect.getsource(build_plan_from_json)
        self.assertIn("_looks_like_sectioned_client_data", source,
                      "build_plan_from_json no longer branches on sectioned data; "
                      "re-check which parser these synthetic plans reach")

        section_keys = {"Household", "Economic Assumptions", "Model Constants",
                        "Social Security", "Assets", "Income", "Spending",
                        "Withdrawal Policy", "Estate Planning"}
        for name, scenario in SCENARIOS.items():
            with self.subTest(case=name):
                plan = scenario.plan()
                self.assertFalse(
                    section_keys & set(plan),
                    f"{name} uses a reserved section key and would be parsed as "
                    f"sectioned client data",
                )
                nested = [
                    k for k, v in plan.items()
                    if isinstance(v, dict) and any(isinstance(x, dict) for x in v.values())
                ]
                self.assertEqual(
                    nested, [],
                    f"{name} has a dict-of-dicts at {nested}, which trips "
                    f"_looks_like_sectioned_client_data and routes into parse_client",
                )

    def test_gate_runs_against_a_workspace_with_no_client_files(self):
        with empty_workspace() as ws:
            self.assertEqual(list((ws / "input").iterdir()), [])
            with frozen_holdings_prices():
                metrics = project_metrics(SCENARIOS["baseline_balanced_couple"].build())
        self.assertGreater(metrics["terminal_total_nw"], 0.0)


class SyntheticGoldenMasterTests(unittest.TestCase):
    def test_golden_master_library_covers_multiple_plan_stresses(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(expected), sorted(SCENARIOS),
            "the pinned fixture and the scenario registry have drifted apart; "
            "regenerate tests/fixtures/synthetic_golden_master_cases.json",
        )

        with empty_workspace():
            actual = {}
            for name, scenario in SCENARIOS.items():
                # Holdings prices are pinned to the committed snapshot
                # (tests/golden_pricing.py) — the same pin test_2 uses — so the
                # synthetic tax lots in the TLH scenario are valued exactly.
                with frozen_holdings_prices():
                    actual[name] = project_metrics(scenario.build())

        for name, expected_metrics in expected.items():
            with self.subTest(case=name):
                for key, expected_value in expected_metrics.items():
                    if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                        # MEASURED, not assumed. These configs are built in code
                        # and priced from a frozen snapshot, so there is no
                        # remaining source of run-to-run variance. Observed
                        # spread was exactly 0.00 on every metric across: 4
                        # repeats in one process, 3 separate processes, and
                        # CPython 3.12 and 3.14 (the two interpreters installed
                        # here; CI runs 3.11 and 3.14). The old plan-coupled
                        # library carried delta=50000.0 to absorb its coupling
                        # to input/ — that slack is not needed here and would
                        # hide real regressions, so this asserts to the cent.
                        self.assertAlmostEqual(
                            actual[name][key], expected_value, places=2,
                            msg=f"{name}.{key}",
                        )
                    else:
                        self.assertEqual(actual[name][key], expected_value, f"{name}.{key}")

    def test_every_scenario_is_distinguishable_from_the_baseline(self):
        """A scenario whose override silently stopped applying is worthless.

        Each non-baseline scenario must move at least one pinned dollar metric,
        otherwise it is a duplicate of the baseline dressed up with a docstring
        and contributes no coverage.
        """
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        baseline = expected["baseline_balanced_couple"]
        money_keys = ("terminal_total_nw", "terminal_liquid_nw", "lifetime_tax",
                      "total_roth_conversion", "first_year_total_tax")
        for name, metrics in expected.items():
            if name == "baseline_balanced_couple":
                continue
            with self.subTest(case=name):
                self.assertTrue(
                    any(metrics[k] != baseline[k] for k in money_keys),
                    f"{name} produces the same dollar metrics as the baseline; "
                    f"its override is not reaching the engine",
                )

    def test_every_scenario_documents_what_it_exercises(self):
        for name, scenario in SCENARIOS.items():
            with self.subTest(case=name):
                self.assertGreater(
                    len(scenario.doc), 80,
                    f"{name} needs a docstring stating what it exercises and why",
                )


if __name__ == "__main__":
    unittest.main()
