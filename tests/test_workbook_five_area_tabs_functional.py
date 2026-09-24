import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def _sheet_names(xlsx_path: Path):
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(xlsx_path) as zf:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
    return [s.attrib["name"] for s in root.find("a:sheets", ns)]


@pytest.mark.slow
def test_output_workbook_uses_numbered_top_level_area_tabs(built_workbook_path):
    assert built_workbook_path.exists(), f"Expected generated workbook at {built_workbook_path}"
    names = _sheet_names(built_workbook_path)

    expected_sections = [
        "1. Reports",
        "2. Optimizers",
        "3. Comparisons",
        "4. Risks",
        "5. Reference",
    ]
    for section in expected_sections:
        assert section in names

    assert names[:7] == [
        "1. Reports",
        "1A. Executive Summary",
        "1B. Net Worth",
        "1C. Cash Flow",
        "1D. Balance Sheet",
        "1E. Charts",
        "1F. Lifetime Taxes",
    ]
    assert names[names.index("2. Optimizers") + 1] == "2A. Roth Conversion"
    assert names[names.index("3. Comparisons") + 1] == "3A. State Residency"
    assert names[names.index("4. Risks") + 1] == "4A. Monte Carlo"
    assert names[names.index("5. Reference") + 1] == "5A. Plan Data"
    assert names[-1] == "_Chart Dashboard Data"


def test_source_layout_declares_same_numbered_areas():
    # #209/#210/#212/#228: WORKBOOK_SECTION_LAYOUT now lists each sheet's
    # STABLE (build-time) name -- letters (1A, 2E, 3C, 4G, ...) are computed
    # fresh per build from whichever sheets survive module gating, not
    # hard-coded here. System review 2026-08-04 (`sheet-identity-scattered-
    # across-five-tables`, Wave 4.3): the table is now derived at import time
    # from module_catalog.SHEET_REGISTRY, so this reads the live runtime
    # value rather than parsing source text for a literal that no longer
    # exists as one.
    from src.reporting.workbook_common import WORKBOOK_SECTION_LAYOUT as layout
    assert [a["section"] for a in layout] == [
        "1. Reports",
        "2. Optimizers",
        "3. Comparisons",
        "4. Risks",
        "5. Reference",
    ]
    flattened = [sheet for area in layout for sheet in area["sheets"]]
    assert flattened[:3] == ["1. Executive Summary", "5. Net Worth Projection", "6. Cash Flow Projection"]
    # W3 (#329 O10, F1): COMPARISON modules get their own group, out of
    # Optimizers -- S-Corp vs LLC and State Residency now sit in Comparisons.
    assert "S-Corp vs LLC" in flattened
    assert "19. Life Insurance" in flattened
    # W3 split LTC Stress Test back out of the merged Life Insurance sheet
    # (#329 O10) -- both are now independent Risks entries.
    assert "17. LTC Stress Test" in flattened
    # W11 addendum (2026-09-22): '27. Planning Levers' was found to be a real,
    # actively-used interactive lever-screening tool, not the static
    # provenance echo every upstream doc (including this one, previously)
    # assumed -- see docs/superpowers/plans/2026-09-22-w11-planning-levers-
    # retirement-notes.md. Kept, and recatalogued WORKSHEET (was REFERENCE),
    # which moves it out of System and into Reports, densely last there
    # (its exact '1I.' position is pinned in
    # test_workbook_numbered_section_tabs_functional.py, not here). '11B. Tax
    # Capacity' is still REFERENCE-kind (filed in System rather than Reports)
    # and, with Planning Levers gone, is now densely last in System itself.
    assert flattened[-1] == "11B. Tax Capacity"
    assert flattened[-2] == "22. Glossary"
    assert flattened[-3] == "23. Methodology"
