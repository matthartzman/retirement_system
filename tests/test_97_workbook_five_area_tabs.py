import ast
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def _sheet_names(xlsx_path: Path):
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(xlsx_path) as zf:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
    return [s.attrib["name"] for s in root.find("a:sheets", ns)]


def _source_constant(name: str):
    tree = ast.parse(Path("src/reporting/workbook_common.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"Missing {name} constant")


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
    layout = _source_constant("WORKBOOK_SECTION_LAYOUT")
    assert [a["section"] for a in layout] == [
        "1. Reports",
        "2. Optimizers",
        "3. Risk & Stress Tests",
        "4. System",
    ]
    flattened = [sheet for area in layout for sheet in area["sheets"]]
    assert flattened[:3] == ["1A. Executive Summary", "1B. Net Worth", "1C. Cash Flow"]
    assert "2E. S-Corp vs LLC" in flattened
    assert "3C. LTC + Life Insurance" in flattened
    assert flattened[-1] == "4G. Glossary"
