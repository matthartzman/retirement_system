"""Slice: Monarch field map -> table ``monarch_field_map`` (WP3.8).

Source: ``reference_src/monarch_field_map.json`` (the column mapping dict as JSON).
Stored as a key/value table with JSON text in the ``data`` column.

Getter: ``src/stores/ref_getters/monarch_field_map.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

SOURCES = ("monarch_field_map.json",)


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    """Build monarch_field_map table from JSON source."""
    with open(src / "monarch_field_map.json", "r", encoding="utf-8") as fh:
        field_map = json.load(fh)

    # Store the entire field map as a single JSON blob
    # The getter will deserialize this
    rows = [
        (0, json.dumps(field_map))  # seq=0, data=JSON string
    ]

    return {"monarch_field_map": (["seq", "data"], rows)}
