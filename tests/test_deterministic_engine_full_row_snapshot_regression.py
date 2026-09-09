"""Full per-year row snapshot regression -- prerequisite for ticket 3.10.

See
``docs/superpowers/plans/2026-09-08-deterministic-engine-stage-decomposition-design.md``
for the full rationale. Short version: both pre-existing golden-master
suites (``test_frozen_sample_plan_golden_master_regression.py`` and
``test_synthetic_golden_master.py``) pin only ~10 AGGREGATE scalars per
scenario (terminal net worth, lifetime tax, first RMD year/amount, ...).
Neither pins any per-year INTERMEDIATE field -- account balances, IRMAA
tier, spend-by-tier breakdown, effective marginal rate, etc. A future
stage-extraction PR (splitting
``run_deterministic_projection_stage()`` in
``src/projection_stages/deterministic_engine.py`` into smaller functions)
could subtly change an intermediate field's value or timing while still
preserving those ~10 aggregates, and neither existing suite would notice.

This test snapshots the ENTIRE per-year ``rows`` output -- every field of
every year's row dict -- for a small set of scenarios already covered by
the synthetic golden master (``tests/synthetic_plans.py``), rather than
inventing new plan configs. Every future stage-extraction PR (per the
design doc's extraction order) must keep this test green; per the design
doc, any pinned-value drift is a bug in the extraction, not something to be
waved through by regenerating the fixture.

Scenario selection
-------------------
Three scenarios already in ``tests/synthetic_plans.SCENARIOS``, chosen for
distinct engine paths so a stage bug that only shows up under one condition
is still caught:

- ``baseline_balanced_couple`` -- MFJ couple, pre-tax heavy, RMDs and
  Roth conversions both active. The main control case.
- ``single_filer`` -- one-member household filing Single, a different
  (smaller) account/income/spending shape and a different bracket table.
  The simplest scenario in the library.
- ``early_survivor_compression`` -- Member 1 dies in year 6, exercising the
  MFJ-to-Single survivor transition, inherited-account handling, and the
  first_death_done/filing state that persists across years -- exactly the
  kind of cross-year mutable state the design doc calls out as high risk
  for stages 1-2.
- ``tax_loss_harvesting`` -- added 2026-09-09 per the Stage 10 sub-stage #6
  design addendum. TLH and 0%-bracket gain harvesting both enabled against
  seeded synthetic lots: a large year-1 loss harvest that exceeds that
  year's gains (forcing the $3k ordinary-offset path and a cap-loss
  carryforward sized to outlive the plan's own big-LTCG years), plus an
  appreciated lot that gain-harvests once income drops into 0%-bracket
  headroom while that carryforward is still positive. The only scenario
  pinning the LTCG/NIIT fixed-point loop, TLH, gain harvesting, and the
  cap-loss waterfall at the per-year level -- see
  ``tests/synthetic_plans.py``'s ``_enable_tlh`` docstring for the exact
  mechanics and line-item justification.

Fixture format and regeneration
--------------------------------
``tests/fixtures/deterministic_engine_full_row_snapshot_cases.json`` maps
scenario name -> list of per-year row dicts, exactly as returned by
``src.planning_engines.project(c)``, JSON round-tripped (row dicts here are
plain str/int/float/bool/dict/list/None, so this is lossless other than
float formatting, which the comparison below tolerates).

Nothing in this file writes the fixture. The ONLY sanctioned way to
regenerate it is ``tools/regen_full_row_snapshot.py --reason "..."``, which
refuses to run without a real (non-placeholder, >= 30 char) reason -- the
same safeguard ``tools/regen_golden_master.py`` uses for the other frozen
fixtures in this repo. A hand-edited fixture, or one regenerated without a
recorded reason, defeats the point of this test.

Float tolerance
----------------
Float fields are compared with the same tolerance the two pre-existing
golden-master suites use for their pinned dollar figures:
``round(value, 2)`` (i.e. to the cent) via ``assertAlmostEqual(..., places=2)``.
See ``test_synthetic_golden_master.py``'s
``test_golden_master_library_covers_multiple_plan_stresses`` and
``test_frozen_sample_plan_golden_master_regression.py``'s pinned-figure
assertions -- both already established this as "no remaining source of
run-to-run variance below the cent" for this deterministic, synthetic-input
engine. Non-float fields (str/int/bool/None) are compared exactly.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.platform_runtime import WORKSPACE_SUBDIRS
from tests.golden_pricing import frozen_holdings_prices
from tests.synthetic_plans import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "deterministic_engine_full_row_snapshot_cases.json"

# Kept in sync with tools/regen_full_row_snapshot.py, which imports this name.
SNAPSHOT_SCENARIOS = (
    "baseline_balanced_couple",
    "single_filer",
    "early_survivor_compression",
    # Added 2026-09-09 per the Stage 10 sub-stage #6 design addendum
    # ("Recommended regression-test coverage"): the only scenario that
    # exercises the LTCG/NIIT fixed-point loop, TLH, gain harvesting, and
    # the cap-loss carryforward waterfall -- the highest-risk piece of the
    # withdrawal cascade still inline, and previously unpinned at the
    # per-year level.
    "tax_loss_harvesting",
)

FLOAT_PLACES = 2  # cents -- matches the tolerance both existing golden masters use.


@contextlib.contextmanager
def empty_workspace():
    """Same isolation as test_synthetic_golden_master.py's helper of the same name.

    Reimplemented here (rather than imported from that module) so this file
    has no import-time dependency on another test module's internals; the
    behavior is intentionally identical -- point the workspace at an empty
    tree so an accidental read of client data under ``input/`` fails loudly
    instead of silently repricing the snapshot.
    """
    saved = os.environ.get("RETIREMENT_SYSTEM_WORKSPACE_ROOT")
    with tempfile.TemporaryDirectory(prefix="full_row_snapshot_") as tmp:
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


def _compute_snapshots() -> dict:
    """Recompute rows for every snapshot scenario. Read-only -- never writes the fixture."""
    from src.planning_engines import project

    snapshots = {}
    with empty_workspace():
        for name in SNAPSHOT_SCENARIOS:
            scenario = SCENARIOS[name]
            with frozen_holdings_prices():
                rows = project(scenario.build())
            snapshots[name] = rows
    return snapshots


def _json_roundtrip(rows):
    """Normalize the same way the fixture on disk was normalized (JSON round-trip)."""
    return json.loads(json.dumps(rows))


def _diff_rows(scenario: str, expected_rows: list, actual_rows: list) -> list[str]:
    """Return a list of human-readable diff lines: exactly what field, what year, what changed.

    Deliberately does not stop at the first mismatch -- a stage-extraction bug
    that moves several fields at once should show all of them in one failure,
    not force a fix-rerun-fix loop.
    """
    problems: list[str] = []

    if len(expected_rows) != len(actual_rows):
        problems.append(
            f"[{scenario}] row count differs: expected {len(expected_rows)}, "
            f"got {len(actual_rows)}"
        )

    for i, (expected_row, actual_row) in enumerate(zip(expected_rows, actual_rows)):
        year = actual_row.get("year", expected_row.get("year", f"index {i}"))
        expected_keys = set(expected_row)
        actual_keys = set(actual_row)
        if expected_keys != actual_keys:
            missing = sorted(expected_keys - actual_keys)
            added = sorted(actual_keys - expected_keys)
            if missing:
                problems.append(f"[{scenario}] year {year}: fields missing from actual row: {missing}")
            if added:
                problems.append(f"[{scenario}] year {year}: unexpected new fields in actual row: {added}")

        for key in sorted(expected_keys & actual_keys):
            problems.extend(
                _diff_value(f"[{scenario}] year {year} field {key!r}",
                            expected_row[key], actual_row[key])
            )

    return problems


def _diff_value(path: str, expected, actual) -> list[str]:
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            expected_f = float(expected)
            actual_f = float(actual)
        except (TypeError, ValueError):
            if expected != actual:
                return [f"{path}: expected {expected!r}, got {actual!r}"]
            return []
        if round(expected_f - actual_f, FLOAT_PLACES) != 0:
            return [f"{path}: expected {expected_f!r}, got {actual_f!r} "
                    f"(diff {actual_f - expected_f:+.6f}, tolerance is {FLOAT_PLACES} decimal places)"]
        return []

    if isinstance(expected, dict) and isinstance(actual, dict):
        problems = []
        expected_keys = set(expected)
        actual_keys = set(actual)
        if expected_keys != actual_keys:
            missing = sorted(expected_keys - actual_keys)
            added = sorted(actual_keys - expected_keys)
            if missing:
                problems.append(f"{path}: sub-keys missing from actual: {missing}")
            if added:
                problems.append(f"{path}: unexpected new sub-keys in actual: {added}")
        for k in sorted(expected_keys & actual_keys):
            problems.extend(_diff_value(f"{path}[{k!r}]", expected[k], actual[k]))
        return problems

    if isinstance(expected, list) and isinstance(actual, list):
        problems = []
        if len(expected) != len(actual):
            problems.append(f"{path}: list length differs: expected {len(expected)}, got {len(actual)}")
        for idx, (e, a) in enumerate(zip(expected, actual)):
            problems.extend(_diff_value(f"{path}[{idx}]", e, a))
        return problems

    if expected != actual:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


@pytest.mark.golden_master
class DeterministicEngineFullRowSnapshotTests(unittest.TestCase):
    """Pins every per-year field of `rows` for a handful of synthetic scenarios.

    This is the ticket 3.10 step-1 prerequisite: gate every stage-extraction
    PR on this test staying green, in addition to the two existing
    golden-master suites (which alone would not catch an intermediate-field
    regression -- see module docstring).
    """

    def test_fixture_covers_the_declared_scenarios(self):
        self.assertTrue(FIXTURE.exists(), f"missing fixture: {FIXTURE}")
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(expected), sorted(SNAPSHOT_SCENARIOS),
            "the pinned fixture and SNAPSHOT_SCENARIOS have drifted apart; "
            "regenerate via `python tools/regen_full_row_snapshot.py --reason ...` "
            "after updating SNAPSHOT_SCENARIOS",
        )

    def test_full_row_snapshot_is_unchanged(self):
        """The whole point: every field, every year, byte-for-byte (floats to the cent)."""
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        actual = _json_roundtrip(_compute_snapshots())

        problems: list[str] = []
        for name in SNAPSHOT_SCENARIOS:
            self.assertIn(name, expected, f"fixture is missing scenario {name!r}")
            self.assertIn(name, actual, f"failed to compute scenario {name!r}")
            problems.extend(_diff_rows(name, expected[name], actual[name]))

        if problems:
            header = (
                f"Full-row snapshot regression: {len(problems)} field(s)/row(s) differ from "
                f"the pinned fixture at {FIXTURE.relative_to(ROOT)}.\n"
                "If this is an intentional engine change (not a stage-extraction bug), "
                "regenerate via:\n"
                "    python tools/regen_full_row_snapshot.py --reason \"<why>\"\n"
                "Diffs:\n"
            )
            self.fail(header + "\n".join(problems))

    def test_snapshot_scenarios_are_reused_from_the_synthetic_library(self):
        """Guards against silently drifting to ad-hoc, uncovered plan configs.

        The whole point of reusing tests/synthetic_plans.py scenarios is that
        they are ALREADY exercised (and independently pinned at the aggregate
        level) by test_synthetic_golden_master.py -- this test only adds
        per-year field coverage on top of scenarios that already exist for
        other reasons, rather than inventing new ones nobody else maintains.
        """
        for name in SNAPSHOT_SCENARIOS:
            self.assertIn(
                name, SCENARIOS,
                f"{name!r} must be a scenario defined in tests/synthetic_plans.SCENARIOS",
            )


if __name__ == "__main__":
    unittest.main()
