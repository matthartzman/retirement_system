"""Item 262: the testing-tier policy (which change needs which test level,
and the parallelized full-suite command) must stay documented and wired up,
not just decided once and forgotten.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _claude_md() -> str:
    return (ROOT / "documentation" / "CLAUDE.md").read_text(encoding="utf-8")


def test_claude_md_documents_change_level_to_test_tier_table():
    doc = _claude_md()
    assert "What level of change needs what level of testing" in doc
    assert "Targeted tier" in doc
    assert "Fast tier" in doc
    assert "Full suite" in doc


def test_claude_md_full_suite_command_uses_xdist_parallelism():
    doc = _claude_md()
    assert "pytest tests/ -n auto --tb=short -q" in doc
    assert "WinError 5" in doc  # documents the known Windows file-lock flake


def test_pytest_xdist_is_a_declared_dev_dependency():
    req = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest-xdist" in req


def test_test_naming_convention_is_documented_and_enforced():
    doc = _claude_md()
    assert "test_<succinct_scope>_<type>.py" in doc
    assert (ROOT / "tests" / "test_no_tracking_id_test_names_regression.py").exists()
