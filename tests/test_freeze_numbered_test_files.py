"""Q2 (system review 2026-07-21): freeze-and-fix-forward for the numbered
test-file convention (test_<N>_description.py), rather than the XL effort of
renaming/reorganizing the existing ~145 such files by subsystem.

The numbered convention accreted with no organizing principle beyond "when
this roadmap item shipped" -- e.g. allocation behavior alone is spread across
13+ separate test_<N>_*.py files. Freezing the set means new coverage lands
in a subsystem-named file (test_<topic>.py, no number) instead of growing
that scatter further. This test is the enforcement: it fails if a new
test_<N>_*.py file appears that isn't already grandfathered in the baseline.

To add genuinely new coverage: create or extend a subsystem-named file
instead. If a new numbered file is truly unavoidable, add its name to
tests/fixtures/numbered_test_files_baseline.json in the same change --
that's a deliberate, reviewable opt-out, not a silent ratchet loosening.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
BASELINE_PATH = TESTS_DIR / "fixtures" / "numbered_test_files_baseline.json"
NUMBERED_PATTERN = re.compile(r"^test_\d+_.*\.py$")


def _current_numbered_files() -> set[str]:
    return {p.name for p in TESTS_DIR.glob("test_*.py") if NUMBERED_PATTERN.match(p.name)}


def _baseline_files() -> set[str]:
    return set(json.loads(BASELINE_PATH.read_text(encoding="utf-8")))


def test_no_new_numbered_test_files_beyond_the_frozen_baseline():
    new_files = sorted(_current_numbered_files() - _baseline_files())
    assert new_files == [], (
        f"New numbered test file(s) found that aren't in the frozen baseline: {new_files}. "
        "Land new coverage in a subsystem-named file (test_<topic>.py) instead of growing "
        "the test_<N>_*.py scatter. If a numbered file is genuinely unavoidable, add its name "
        f"to {BASELINE_PATH.relative_to(ROOT)} in the same change."
    )


def test_baseline_only_lists_files_that_still_exist():
    # Catches typos/stale entries in the baseline itself -- not load-bearing
    # for the freeze (removals are always allowed), just keeps the fixture honest.
    stale = sorted(name for name in _baseline_files() if not (TESTS_DIR / name).exists())
    assert stale == [], f"Baseline lists file(s) that no longer exist: {stale}"
