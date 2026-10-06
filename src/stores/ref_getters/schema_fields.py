"""Field schema and field tiers from ``reference.db`` (WP3.7).

Table ``schema_field`` (built by ``tools/reference_slices/schema_fields.py``).
``schema_fields`` returns what ``schema_registry.load_schema`` always returned:
``{(section, subsection, label): {section, subsection, label, type, required, default,
min, max, description}}`` (all ``str``), in catalog order, fresh dicts on every call.
``field_tiers`` is the new part: ``{(section, subsection, label): min_tier}``.
"""
from __future__ import annotations

from ..ref_access import reference
from ..ref_data import RefData

FIELDS = ("section", "subsection", "label", "type", "required", "default", "min", "max", "description")
TIERS = ("simple", "standard", "advanced", "expert")  # cumulative: a field shows at its tier and above


def schema_fields(ref: RefData | None = None) -> dict[tuple[str, str, str], dict[str, str]]:
    ref = reference() if ref is None else ref
    sel = ", ".join(f'"{c}"' for c in FIELDS)
    out: dict[tuple[str, str, str], dict[str, str]] = {}
    for r in ref.query(f'SELECT {sel} FROM "schema_field" ORDER BY seq'):
        row = {c: r[c] for c in FIELDS}
        out[(row["section"].strip(), row["subsection"].strip(), row["label"].strip())] = row
    return out


def field_tiers(ref: RefData | None = None) -> dict[tuple[str, str, str], str]:
    ref = reference() if ref is None else ref
    return {(r["section"].strip(), r["subsection"].strip(), r["label"].strip()): r["min_tier"]
            for r in ref.query('SELECT section, subsection, label, min_tier FROM "schema_field" ORDER BY seq')}
