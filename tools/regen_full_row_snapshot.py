#!/usr/bin/env python
"""Regeneration tool for the full-row engine snapshot fixture.

Ticket 3.10 step 1. See
``docs/superpowers/plans/2026-09-08-deterministic-engine-stage-decomposition-design.md``
for why this fixture exists: the two pre-existing golden-master suites only
pin ~10 aggregate scalars per scenario and would not notice a stage
extraction that quietly changed an intermediate per-year field (an account
balance, IRMAA tier, spend-by-tier breakdown, ...). This fixture pins every
field of every year's row dict instead, for a handful of scenarios already
covered by ``tests/synthetic_plans.py``.

This script is the ONLY sanctioned way to rewrite
``tests/fixtures/deterministic_engine_full_row_snapshot_cases.json``. Nothing
in the test suite writes it automatically -- see
``tests/test_deterministic_engine_full_row_snapshot_regression.py``, which
only reads and compares. Mirrors the safeguard ``tools/regen_golden_master.py``
uses for the other frozen fixtures: this refuses to run without an explicit,
non-placeholder ``--reason``, so a pin can never move silently.

Usage
-----
    python tools/regen_full_row_snapshot.py --reason "<why this changed>"

Always confirm you MEANT the values to change before running this -- if the
new rows differ from the old ones because of an unintended engine change,
the fix is to fix the engine, not to regenerate the pin.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "deterministic_engine_full_row_snapshot_cases.json"

sys.path.insert(0, str(ROOT))

# Same exact-match / substring placeholder guards as tools/regen_golden_master.py,
# kept in sync deliberately -- a reason that would be rejected for one frozen
# fixture in this repo should be rejected for all of them.
_PLACEHOLDER_REASONS = {
    "todo", "tbd", "n/a", "na", "reason", "test", "testing", "placeholder",
    "asdf", "wip", "fix", "update", "regen", "update pin", "changed",
}
_PLACEHOLDER_MARKERS = ("todo", "tbd", "fixme", "xxx", "placeholder", "wip", "n/a")
_PLACEHOLDER_MARKER_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(m) for m in _PLACEHOLDER_MARKERS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)
MIN_REASON_LEN = 30


def _validate_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise SystemExit("Refusing: --reason is required and must not be empty.")
    if reason.strip().lower() in _PLACEHOLDER_REASONS:
        raise SystemExit(f"Refusing: {reason!r} is a placeholder, not a real justification.")
    if _PLACEHOLDER_MARKER_RE.search(reason):
        raise SystemExit(f"Refusing: {reason!r} contains a placeholder marker (todo/tbd/wip/...).")
    if len(reason) < MIN_REASON_LEN:
        raise SystemExit(
            f"Refusing: --reason is only {len(reason)} chars; give a real justification "
            f"(>= {MIN_REASON_LEN} chars) -- e.g. which stage-extraction PR this pins."
        )
    return reason


def _compute_snapshots() -> dict:
    """The single source of truth for how the fixture is computed.

    Reused verbatim by the test file's own comparison path -- see
    ``tests/test_deterministic_engine_full_row_snapshot_regression.py``'s
    ``_compute_snapshots``, which imports this function rather than
    reimplementing the measurement.
    """
    os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")
    from tests.golden_pricing import frozen_holdings_prices
    from tests.synthetic_plans import SCENARIOS
    from src.planning_engines import project

    from tests.test_deterministic_engine_full_row_snapshot_regression import (
        SNAPSHOT_SCENARIOS,
        empty_workspace,
    )

    snapshots = {}
    with empty_workspace():
        for name in SNAPSHOT_SCENARIOS:
            scenario = SCENARIOS[name]
            with frozen_holdings_prices():
                rows = project(scenario.build())
            snapshots[name] = rows
    return snapshots


def cmd_regen(args) -> int:
    reason = _validate_reason(args.reason)
    snapshots = _compute_snapshots()
    FIXTURE.write_text(
        json.dumps(snapshots, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {FIXTURE.relative_to(ROOT)} ({FIXTURE.stat().st_size:,} bytes).")
    print(f"Reason: {reason}")
    print(
        "Remember to record this regeneration (commit message, changelog, or PR "
        "description) -- this tool does not append to a changelog file on its own."
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reason", required=True,
        help="Why the fixture is being regenerated. Required, non-placeholder, >= 30 chars.",
    )
    args = parser.parse_args(argv)
    return cmd_regen(args)


if __name__ == "__main__":
    raise SystemExit(main())
