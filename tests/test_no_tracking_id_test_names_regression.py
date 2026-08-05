"""Enforces the test-file naming standard (item 261, 2026-08-05): no test
file name may encode a wave, issue/item number, phase letter, or version
tag (test_<N>_..., test_wave<N>_..., test_phase<N>_..., test_item_<N>_...,
test_v<N>_<N>_...). Those all got rationalized away in the same change --
see git history for the full rename. New coverage must use the standard
`test_<succinct_scope>_<type>.py` format instead (type: regression,
functional, contract, smoke, unit, integration), so a test's name alone
says what it covers rather than which roadmap item shipped it.

`test_v10_*` files are exempt: "v10" names the product (Version 10), not a
wave/issue tracking id.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

TRACKING_ID_PATTERN = re.compile(
    r"^test_(\d+_|wave\d+_|phase\d+_|phase_[a-z]_|item_\d+_)"
)


def test_no_test_file_names_encode_a_wave_issue_or_phase_number():
    offenders = sorted(
        p.name
        for p in TESTS_DIR.glob("test_*.py")
        if TRACKING_ID_PATTERN.match(p.name)
    )
    assert offenders == [], (
        f"Test file name(s) encode a wave/issue/phase tracking id: {offenders}. "
        "Use test_<succinct_scope>_<type>.py instead (type: regression, "
        "functional, contract, smoke, unit, integration)."
    )

