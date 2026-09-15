"""tests/e2e/*.spec.js must not grow its count of real workbook-build triggers.

E2E efficiency review (2026-09-15), recommendation R9. A real build costs
~110s (see tests/e2e/helpers.js's triggerBuildAndWaitForOverlay), and before
this review the suite ran FOUR of them across 22 tests -- three of which
existed only to make a workbook exist so some other page had data to show,
not because the build itself was under test (see tools/e2e_server.py's
module docstring, which now does that one setup build itself). Nothing
stopped a new spec from adding a fifth "just build it real quick" call the
same way.

This is a ratchet, not a budget: the ceiling only ever moves DOWN (when a
spec is consolidated the way the three were) or is deliberately raised WITH
a comment explaining why a new call site genuinely needs its own real build
(matching the pattern documentation/reference/CLAUDE.md's frontend-size
ratchet already establishes for dashboard.js). It counts call sites to the
shared helper, not literal builds -- tests/e2e/build-failure.spec.js's call
intercepts the build API routes (page.route(...)) and never spawns a real
subprocess, but it still counts here deliberately: a future edit that
removes the interception and lets it become a real build should be caught
by this ceiling too, not silently exempted because the call site already
existed.

Do NOT raise BUILD_TRIGGER_CALL_SITE_MAX to make a new spec's build pass --
that is the drift this test exists to prevent. Either make the new spec use
an already-built workbook (see openCurrentPlan()/e2e_server.py's own
pre-build) or justify the new real build in a comment on this ceiling.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E2E_DIR = ROOT / "tests" / "e2e"

# 2026-09-15: set at the post-consolidation count. build-and-results.spec.js
# (the one spec that genuinely tests the UI-triggered build flow) and
# workbook-format-stale-cache.spec.js's second build (the actual
# cache-invalidation regression under test) trigger real builds;
# build-failure.spec.js's call is against intercepted/synthetic routes.
BUILD_TRIGGER_CALL_SITE_MAX = 3

_CALL_PATTERN = re.compile(r"triggerBuildAndWaitForOverlay\s*\(")


def _call_site_count() -> int:
    total = 0
    for spec in E2E_DIR.glob("*.spec.js"):
        total += len(_CALL_PATTERN.findall(spec.read_text(encoding="utf-8")))
    return total


def test_e2e_build_trigger_call_sites_do_not_grow():
    actual = _call_site_count()
    assert actual <= BUILD_TRIGGER_CALL_SITE_MAX, (
        f"tests/e2e/*.spec.js call triggerBuildAndWaitForOverlay {actual} times, "
        f"over the {BUILD_TRIGGER_CALL_SITE_MAX}-call ratchet by "
        f"{actual - BUILD_TRIGGER_CALL_SITE_MAX}. Each real build costs ~110s; "
        "a new spec that needs an already-built workbook should rely on "
        "tools/e2e_server.py's own startup build (see openCurrentPlan()'s "
        "callers that never trigger a build) rather than adding another one. "
        "Do NOT raise BUILD_TRIGGER_CALL_SITE_MAX without a comment here "
        "justifying why the new call site genuinely needs its own real build."
    )


def test_ratchet_target_exists():
    assert E2E_DIR.is_dir(), "tests/e2e/ not found -- update this ratchet's path if it moved."
    assert list(E2E_DIR.glob("*.spec.js")), "no *.spec.js files found under tests/e2e/."
