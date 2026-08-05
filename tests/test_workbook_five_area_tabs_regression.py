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
        "3. Risk & Stress Tests",
        "4. System",
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
    assert names[names.index("3. Risk & Stress Tests") + 1] == "3A. Monte Carlo"
    assert names[names.index("4. System") + 1] == "4A. Plan Data"
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
        "3. Risk & Stress Tests",
        "4. System",
    ]
    flattened = [sheet for area in layout for sheet in area["sheets"]]
    assert flattened[:3] == ["1. Executive Summary", "5. Net Worth Projection", "6. Cash Flow Projection"]
    assert "S-Corp vs LLC" in flattened
    assert "19. Life Insurance" in flattened
    assert flattened[-1] == "22. Glossary"
