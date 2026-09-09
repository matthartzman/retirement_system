#!/usr/bin/env python
"""Regeneration tool for the synthetic golden-master fixture.

``tests/fixtures/synthetic_golden_master_cases.json`` pins ~10 aggregate
metrics per scenario in ``tests/synthetic_plans.SCENARIOS`` (see
``tests/test_synthetic_golden_master.py``). Unlike the two other frozen
fixtures in this repo, this one previously had no dedicated, gated
regeneration tool -- it was updated by hand-rolled one-off scripts run
inline, which is exactly the kind of silent-pin-move
``tools/regen_golden_master.py`` and ``tools/regen_full_row_snapshot.py``
both exist to prevent for their own fixtures. This tool closes that gap,
mirroring their safeguard: it refuses to run without an explicit,
non-placeholder ``--reason``, so a pin can never move without a recorded
justification.

Usage
-----
    python tools/regen_synthetic_golden_master.py --reason "<why this changed>"

Always confirm you MEANT the values to change before running this -- if the
new metrics differ from the old ones because of an unintended engine
change, the fix is to fix the engine, not to regenerate the pin.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_golden_master_cases.json"

sys.path.insert(0, str(ROOT))

# Same exact-match / substring placeholder guards as
# tools/regen_golden_master.py and tools/regen_full_row_snapshot.py, kept in
# sync deliberately -- a reason that would be rejected for one frozen
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
            f"(>= {MIN_REASON_LEN} chars) -- e.g. which scenario/engine change this pins."
        )
    return reason


def _compute_metrics() -> dict:
    """The single source of truth for how the fixture is computed.

    Mirrors ``test_synthetic_golden_master.py``'s
    ``test_golden_master_library_covers_multiple_plan_stresses`` measurement
    path exactly (same isolation, same frozen pricing) so this tool and that
    test can never disagree about what "the computed value" means.
    """
    os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")
    from tests.golden_pricing import frozen_holdings_prices
    from tests.synthetic_plans import SCENARIOS, project_metrics
    from tests.test_synthetic_golden_master import empty_workspace

    metrics = {}
    with empty_workspace():
        for name, scenario in SCENARIOS.items():
            with frozen_holdings_prices():
                metrics[name] = project_metrics(scenario.build())
    return metrics


def cmd_regen(args) -> int:
    reason = _validate_reason(args.reason)
    metrics = _compute_metrics()
    FIXTURE.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
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
