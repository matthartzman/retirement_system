"""Mechanical suffix-shape checker for test file names (item 2.15, finding
Q6: "Add Option 2 [a mechanical suffix-shape checker] afterwards to stop it
re-inflating").

Q6 found the `_regression` suffix conflated three different things (golden-
master comparisons, grep-based DOM-literal pinning, and genuine bug-fix
regression tests) across 159 of 313 files -- 51% of the whole suite. The
review's own target shape (documentation/reports/SYSTEM_REVIEW_2026-08-31.md
section 5.5) is a "_regression vs _functional rename pass with a mechanical
suffix-shape checker to stop it re-inflating." The 159-file semantic
reclassification (which files are a documented prior bug fix vs. a
structural/DOM check) is a separate, judgment-heavy pass not done by this
checker -- see `documentation/CLAUDE.md`'s test-naming section, which
already documents the type-suffix convention as "not separately enforced"
for existing files.

What THIS checker enforces mechanically, cheaply, and without any semantic
judgment about individual files' content: a ratchet on the count of test
files with NO recognized type suffix (regression/functional/contract/smoke/
unit/integration) at all. That count must never grow. New test files should
pick one of the six types (CLAUDE.md's convention for new files); this stops
the un-suffixed count from re-inflating even before the full historical
rename pass happens, and it moves down over time as files get swept into the
rename pass.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

VALID_TYPES = ("regression", "functional", "contract", "smoke", "unit", "integration")

# Only ever moves DOWN, by renaming a file onto one of the six types in the
# same commit that lowers this number -- never by raising it to make a new
# un-suffixed file pass. One documented exception: merging in an
# independently-developed branch line (2026-09-02, main's #29x/#30x work)
# that predates this checker and was never subject to it brought in several
# new un-suffixed files at once, a one-time reconciliation rather than
# ordinary new-file non-compliance.
LEGACY_NO_SUFFIX_CEILING = 97


def _has_valid_type_suffix(name: str) -> bool:
    return any(name.endswith(f"_{t}.py") for t in VALID_TYPES)


def test_legacy_no_suffix_test_file_count_has_not_grown():
    no_suffix = sorted(
        p.name for p in TESTS_DIR.glob("test_*.py") if not _has_valid_type_suffix(p.name)
    )
    assert len(no_suffix) <= LEGACY_NO_SUFFIX_CEILING, (
        f"{len(no_suffix)} test files now have no recognized type suffix "
        f"(regression/functional/contract/smoke/unit/integration), up from "
        f"the {LEGACY_NO_SUFFIX_CEILING} ceiling. New test files should end "
        "in one of the six types (documentation/CLAUDE.md's test-naming "
        "convention) rather than adding to this legacy count. If this file "
        "was intentionally renamed onto a real type suffix, lower "
        "LEGACY_NO_SUFFIX_CEILING in the same commit."
    )
