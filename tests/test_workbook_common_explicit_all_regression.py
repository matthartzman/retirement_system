"""Finding ARC-5 (system review 2026-09-07, Wave 5 item ARC-5):
src.reporting.workbook_common used to derive `__all__` from
`globals()`, re-exporting every stdlib/openpyxl name the module merely
imports for its own use (csv, math, random, sys, traceback, json, Border,
Side, xl_numbers, ...) as if it were part of the module's genuine public
surface. `__all__` is now an explicit, curated list.
"""
import ast
from pathlib import Path

from src.reporting import workbook_common

ROOT = Path(__file__).resolve().parents[1]


def _names_imported_by_consumers():
    """Every name any src/reporting/*.py file actually pulls in via
    `from .workbook_common import (...)` -- the real, machine-verifiable
    public surface this module needs to keep exporting."""
    names = set()
    for path in (ROOT / "src" / "reporting").glob("*.py"):
        if path.name == "workbook_common.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "workbook_common":
                names.update(alias.name for alias in node.names)
    return names


def test_all_is_not_derived_from_globals():
    # A globals()-derived __all__ would include module-level junk this file
    # imports only for its own internal use, never for re-export.
    assert "csv" not in workbook_common.__all__
    assert "math" not in workbook_common.__all__
    assert "random" not in workbook_common.__all__
    assert "sys" not in workbook_common.__all__
    assert "traceback" not in workbook_common.__all__


def test_all_entries_are_real_module_attributes():
    missing = [name for name in workbook_common.__all__ if not hasattr(workbook_common, name)]
    assert not missing, f"__all__ names not present on the module: {missing}"


def test_all_covers_every_name_a_real_consumer_imports():
    # Every explicit `from .workbook_common import (...)` across src/reporting
    # must keep resolving -- __all__ existing as documentation of that surface
    # would be actively misleading if it silently drifted out of sync.
    consumed = _names_imported_by_consumers()
    missing = consumed - set(workbook_common.__all__)
    assert not missing, f"consumers import names __all__ doesn't list: {missing}"
