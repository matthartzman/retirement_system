"""The number of skip constructs in tests/ must not grow (system review QA-006 / WI-012).

A test that converts a failure into a skip (``skipTest`` after catching an
exception, ``pytest.skip`` when a fixture drifts) silently hides regressions.
This is a ratchet, not a budget: the ceiling only moves DOWN. Adding a skip
means removing another one, or justifying a deliberate, reviewed raise of the
ceiling in the same commit. Do not raise it to make a diff pass.

Skips that are genuinely environmental (no node, no git checkout, Windows-only,
gitignored input/ absent) are counted too; they are the baseline, not exempt.
Do not use a skip to guard against a product or fixture regression -- assert.
"""
from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SELF = Path(__file__).name

# Ratchet DOWN only.
SKIP_CEILING = 37

_SKIP = re.compile(
    r"\.skipTest\(|\bpytest\.skip\(|@pytest\.mark\.skipif\(|@unittest\.skip(?:If|Unless)?\(|"
    r"@pytest\.mark\.skip\(|@pytest\.mark\.requires_live_input\("
)


def _count_skips() -> int:
    total = 0
    for path in sorted(TESTS.rglob("test_*.py")):
        if path.name == SELF:
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            code = line.split("#", 1)[0]
            if _SKIP.search(code):
                total += 1
    return total


def test_skip_count_does_not_grow():
    count = _count_skips()
    assert count <= SKIP_CEILING, (
        f"{count} skip constructs in tests/ exceeds the ceiling of {SKIP_CEILING}. "
        "Assert instead of skipping; skips hide regressions (QA-006)."
    )


def test_ceiling_is_tight():
    """Lower SKIP_CEILING when skips are removed, so the ratchet keeps biting."""
    assert _count_skips() == SKIP_CEILING, (
        f"tests/ now has {_count_skips()} skip constructs; lower SKIP_CEILING to match."
    )
