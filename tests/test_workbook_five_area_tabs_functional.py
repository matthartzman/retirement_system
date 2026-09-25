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

    # #332 W-F Task F6 (design 2026-09-24 §9.1): sheets within a section now
    # order by Topic first -- see test_workbook_numbered_section_tabs_functional.py
    # for the full pinned order and its rationale.
    assert names[:7] == [
        "1. Reports",
        "1A. Spending Summary",
        "1B. Lifetime Taxes",
        "1C. Executive Summary",
        "1D. Net Worth",
        "1E. Cash Flow",
        "1F. Balance Sheet",
    ]
    assert names[names.index("2. Optimizers") + 1] == "2A. Social Security"
    assert names[names.index("3. Comparisons") + 1] == "3A. State Residency"
    assert names[names.index("4. Risks") + 1] == "4A. Monte Carlo"
    assert names[names.index("5. Reference") + 1] == "5A. RMD Audit"
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
    # #332 W-F Task F6 (design 2026-09-24 §9.1): sheets within a section now
    # order by Topic first -- Spending Summary (Spending) and Lifetime Tax
    # (Taxes) sort ahead of the Topic-less ("Whole Plan") Executive Summary.
    assert flattened[:3] == ["29. Spending Summary", "7. Lifetime Tax", "1. Executive Summary"]
    # W3 (#329 O10, F1): COMPARISON modules get their own group, out of
    # Optimizers -- S-Corp vs LLC and State Residency now sit in Comparisons.
    assert "S-Corp vs LLC" in flattened
    assert "19. Life Insurance" in flattened
    # W3 split LTC Stress Test back out of the merged Life Insurance sheet
    # (#329 O10) -- both are now independent Risks entries.
    assert "17. LTC Stress Test" in flattened
    # '11B. Tax Capacity' (Taxes) now sorts with RMD Audit near the front of
    # Reference, ahead of the Topic-less ("Whole Plan") sheets -- see
    # test_workbook_numbered_section_tabs_functional.py for the full order.
    assert flattened[-1] == "22. Glossary"
    assert flattened[-2] == "23. Methodology"
    assert flattened[-3] == "21. Quality Control"
