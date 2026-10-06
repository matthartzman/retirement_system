"""Slice: workbook template layout -> table ``template_layout`` (WP3.8).

Source: ``reference_src/template_layout.json`` (layout data for worksheet formatting).
Stored as a key/value table with JSON text in the ``data`` column.

Getter: ``src/stores/ref_getters/template_layout.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

SOURCES = ("template_layout.json",)


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    """Build template_layout table from JSON source."""
    with open(src / "template_layout.json", "r", encoding="utf-8") as fh:
        template_layout = json.load(fh)

    # Store the entire template layout as a single JSON blob
    # The getter will deserialize this
    rows = [
        (0, json.dumps(template_layout))  # seq=0, data=JSON string
    ]

    return {"template_layout": (["seq", "data"], rows)}
