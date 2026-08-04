"""Workbook sheet identity is duplicated across five tables -- keep them in sync.

System review 2026-08-04, architect finding
`sheet-identity-scattered-across-five-tables`. Adding a sheet today means
editing five places plus a 26-branch dispatch ladder, each carrying the sheet's
name as a bare string:

  workbook_common.V5_LAYOUT               creation order
  workbook_common.WORKBOOK_SECTION_LAYOUT nav grouping
  workbook_common.SHEET_LETTER_ORDER      per-section letter ordering
  workbook_common.FINAL_SHEET_RENAMES     build-name -> final title
  module_catalog.OPTIONAL_MODULE_SHEETS   optional-module gating
  workbook_builder                        the dispatch ladder

The recommendation was Option 1 (a single SHEET_REGISTRY the five tables derive
from) "with Option 2 written first as the safety net: build the consistency
test against the current five tables (it will pass), then introduce
SHEET_REGISTRY and derive the five tables from it -- the test then proves the
derivation is faithful before the dispatch ladder is replaced."

This file is that safety net. It is deliberately written against the CURRENT
shape and must keep passing unchanged across the registry migration; if it has
to be edited to accommodate the registry, the derivation was not faithful.

FINAL_SHEET_RENAMES is intentionally not cross-checked for membership: it is
recomputed per build (workbook_common.py, "Must run once") and is empty at
import time. Asserting on it here would pin import-time state that does not
exist yet, and the registry must preserve that per-build recomputation rather
than freezing renames at import.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.module_catalog import OPTIONAL_MODULE_SHEETS
from src.reporting.workbook_common import (
    SHEET_LETTER_ORDER,
    V5_LAYOUT,
    WORKBOOK_SECTION_LAYOUT,
)

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "src" / "reporting" / "workbook_builder.py"

_DISPATCH = re.compile(r"""if\s+'([^']+)'\s+in\s+sheets:""")
_CREATE_SHEET = re.compile(r"""create_sheet\(\s*'([^']+)'\s*\)""")

# 'H' is not a section: workbook_common.py:161 documents it as the colour code
# for "Hidden/helper sheets". Those are created but deliberately absent from
# SHEET_LETTER_ORDER, which orders the visible nav. A registry migration must
# preserve that distinction rather than inventing a section for them.
HIDDEN_SECTION_CODE = "H"


def _layout_sheets() -> set[str]:
    return {name for name, _code in V5_LAYOUT}


def _created_sheets() -> set[str]:
    """Every sheet the build can produce.

    V5_LAYOUT drives the main creation loop, but a few sheets are created by
    dedicated code paths instead ('S-Corp vs LLC', 'Plan Data'). Treating
    V5_LAYOUT as the complete set would flag those as dangling nav entries when
    they are real.
    """
    return _layout_sheets() | set(_CREATE_SHEET.findall(BUILDER.read_text(encoding="utf-8")))


def _dispatched_sheets() -> set[str]:
    return set(_DISPATCH.findall(BUILDER.read_text(encoding="utf-8")))


def test_layout_is_not_empty():
    assert _layout_sheets(), "V5_LAYOUT is empty; the other assertions would be vacuous"


def test_every_sheet_name_is_unique_in_creation_order():
    names = [name for name, _ in V5_LAYOUT]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"V5_LAYOUT lists the same sheet more than once: {dupes}"


def test_section_layout_only_references_real_sheets():
    known = _created_sheets()
    unknown = sorted(
        f"{section.get('section')} -> {sheet}"
        for section in WORKBOOK_SECTION_LAYOUT
        for sheet in section.get("sheets", [])
        if sheet not in known
    )
    assert not unknown, (
        "WORKBOOK_SECTION_LAYOUT groups sheets that the build never creates, so "
        f"the workbook nav would link to nothing: {unknown}"
    )


def test_every_created_sheet_has_a_known_section_code():
    codes = set(SHEET_LETTER_ORDER) | {HIDDEN_SECTION_CODE}
    orphans = sorted(f"{name} (code {code!r})" for name, code in V5_LAYOUT if code not in codes)
    assert not orphans, (
        "V5_LAYOUT assigns section codes that are neither in SHEET_LETTER_ORDER "
        f"nor the {HIDDEN_SECTION_CODE!r} hidden-sheet sentinel, so their nav "
        f"ordering is undefined: {orphans}"
    )


def test_optional_module_gating_only_names_real_sheets():
    known = _created_sheets()
    unknown = sorted(
        f"{module} -> {sheet}"
        for module, sheets in OPTIONAL_MODULE_SHEETS.items()
        for sheet in (sheets if isinstance(sheets, (list, tuple, set)) else [sheets])
        if sheet not in known
    )
    assert not unknown, (
        "OPTIONAL_MODULE_SHEETS gates sheets that the build never creates. "
        f"Disabling such a module silently gates nothing: {unknown}"
    )


def test_dispatch_ladder_only_builds_real_sheets():
    known = _created_sheets()
    unknown = sorted(_dispatched_sheets() - known)
    assert not unknown, (
        "workbook_builder dispatches on sheet names the build never creates, so "
        f"those branches can never run: {unknown}"
    )


@pytest.mark.parametrize("table", ["V5_LAYOUT", "WORKBOOK_SECTION_LAYOUT", "SHEET_LETTER_ORDER"])
def test_tables_are_populated(table):
    """Guards the guard: an emptied table would make the checks above vacuous."""
    value = {"V5_LAYOUT": V5_LAYOUT, "WORKBOOK_SECTION_LAYOUT": WORKBOOK_SECTION_LAYOUT,
             "SHEET_LETTER_ORDER": SHEET_LETTER_ORDER}[table]
    assert len(value) > 0, f"{table} is empty"
