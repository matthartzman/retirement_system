from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def _chart_root(workbook_path: Path, name: str) -> ET.Element:
    with zipfile.ZipFile(workbook_path) as zf:
        return ET.fromstring(zf.read(f"xl/charts/{name}"))


def _pie_labels_and_values(workbook_path: Path, chart_name: str) -> tuple[list[str], list[float], dict[str, str]]:
    root = _chart_root(workbook_path, chart_name)
    labels = [v.text or "" for v in root.findall(f".//{{{C_NS}}}cat//{{{C_NS}}}v")]
    values = [float(v.text or 0) for v in root.findall(f".//{{{C_NS}}}val//{{{C_NS}}}v")]
    flags = {el.tag.rsplit("}", 1)[-1]: el.get("val") for el in root.findall(f".//{{{C_NS}}}dLbls/*")}
    return labels, values, flags


def test_allocation_pies_do_not_show_series_name_or_zero_slices(built_workbook_path):
    for chart_name in ("chart5.xml", "chart6.xml"):
        labels, values, flags = _pie_labels_and_values(built_workbook_path, chart_name)
        assert flags.get("showSerName") == "0"
        assert flags.get("showLegendKey") == "0"
        assert flags.get("showCatName") == "1"
        assert flags.get("showPercent") == "1"
        assert len(labels) == len(values)
        assert values
        threshold = max(1.0, sum(values) * 0.000001)
        assert all(value > threshold for value in values)

    current_labels, _, _ = _pie_labels_and_values(built_workbook_path, "chart5.xml")
    target_labels, _, _ = _pie_labels_and_values(built_workbook_path, "chart6.xml")
    assert "Bonds" not in current_labels + target_labels
    assert "Short-Term Bonds" not in current_labels + target_labels
    assert "Municipal Bonds" not in current_labels + target_labels
    assert "Managed Futures" not in current_labels + target_labels
    assert "Private Credit" not in current_labels + target_labels
    assert "REITs" not in current_labels + target_labels
    assert "TIPS" not in current_labels + target_labels
