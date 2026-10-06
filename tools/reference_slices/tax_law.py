"""Slice: federal tax-law dataset -> tables ``tax_law_meta``, ``tax_law_value``, ``tax_law_bracket`` (WP3.2).

Source ``reference_src/tax_law_v10.json`` (the dated dataset the annual tax update
edits). Numbers keep their JSON type (int stays int, float stays float) because
the old loader returned them as parsed; an absent ``expires_year`` / open-ended
bracket ``upper`` is NULL. ``seq`` keeps file order (lookups sort stably on it).
Getter: ``src/stores/ref_getters/tax_law.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

from ._source import SliceSourceError

SOURCES = ("tax_law_v10.json",)
VALUE_FIELDS = ("jurisdiction", "filing_status", "name", "value", "effective_year", "expires_year", "source", "status")
BRACKET_FIELDS = ("jurisdiction", "filing_status", "bracket_type", "lower", "upper", "rate", "effective_year",
                  "expires_year", "source", "status")
_OPTIONAL = {"expires_year": None, "upper": None, "source": "local_dataset", "status": "assumption"}


def _rows(items: list, fields: tuple[str, ...], what: str) -> list[tuple]:
    out = []
    for seq, item in enumerate(items):
        extra = set(item) - set(fields)
        missing = [f for f in fields if f not in item and f not in _OPTIONAL]
        if extra or missing:
            raise SliceSourceError(f"tax_law_v10.json {what}[{seq}]: unexpected {sorted(extra)} / missing {missing}")
        out.append((seq, *(item.get(f, _OPTIONAL.get(f)) for f in fields)))
    return out


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    data = json.loads((src / SOURCES[0]).read_text(encoding="utf-8"))
    unknown = set(data) - {"schema", "version", "generated_from", "values", "brackets"}
    if unknown:
        raise SliceSourceError(f"tax_law_v10.json: unexpected top-level keys {sorted(unknown)}")
    meta = [(str(data.get("schema", "tax_law_v10")), str(data.get("version", "v10")),
             str(data.get("generated_from", "unknown")))]
    return {
        "tax_law_meta": (["schema", "version", "generated_from"], meta),
        "tax_law_value": (["seq", *VALUE_FIELDS], _rows(data.get("values", []), VALUE_FIELDS, "values")),
        "tax_law_bracket": (["seq", *BRACKET_FIELDS], _rows(data.get("brackets", []), BRACKET_FIELDS, "brackets")),
    }
