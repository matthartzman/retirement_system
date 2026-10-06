"""Slice: field schema + field tiers -> table ``schema_field`` (WP3.7).

Sources (all under ``reference_src/``):

- ``schema.csv``: the hand-maintained field catalog (authoritative).
- ``generated_schema_coverage.csv``: backfill for plan rows the catalog lacks
  (written by ``tools/generate_schema_coverage.py``); first definition of a key wins.
- ``field_tiers.csv``: ``min_tier`` per field (``simple`` < ``standard`` < ``advanced`` < ``expert``),
  the tag list the owner reviews (design 2026-10-04, decision 8). Every catalog field
  must have exactly one tag and every tag must name a catalog field, or the build fails.

``load_merged`` reproduces the old ``schema_registry.load_schema`` merge exactly
(row cells beyond the header are appended to ``description``). Getter:
``src/stores/ref_getters/schema_fields.py``.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ._source import SliceSourceError

SOURCES = ("schema.csv", "generated_schema_coverage.csv", "field_tiers.csv")
FIELDS = ("section", "subsection", "label", "type", "required", "default", "min", "max", "description")
TIERS = ("simple", "standard", "advanced", "expert")


def _key(row: dict) -> tuple[str, str, str]:
    return ((row.get("section") or "").strip(), (row.get("subsection") or "").strip(), (row.get("label") or "").strip())


def load_merged(src: str | Path, names: tuple[str, ...] = SOURCES[:2]) -> dict[tuple[str, str, str], dict]:
    """``{(section, subsection, label): row}`` merged exactly as ``load_schema`` did
    (``names`` limits which source files take part)."""
    out: dict[tuple[str, str, str], dict] = {}
    for name in names:
        with (Path(src) / name).open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = _key(row)
                if not (key[0] and key[2]) or key in out:
                    continue
                clean = {str(k): v for k, v in dict(row).items() if k is not None}
                extras = row.get(None)
                if extras:
                    desc = str(clean.get("description") or "").strip()
                    extra = ",".join(str(x).strip() for x in extras if str(x).strip())
                    if extra:
                        clean["description"] = (desc + ", " + extra).strip(", ") if desc else extra
                out[key] = clean
    return out


def load_tiers(src: str | Path) -> dict[tuple[str, str, str], str]:
    out: dict[tuple[str, str, str], str] = {}
    with (Path(src) / SOURCES[2]).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["section", "subsection", "label", "min_tier"]:
            raise SliceSourceError(f"field_tiers.csv: unexpected header {reader.fieldnames}")
        for row in reader:
            key = (row["section"], row["subsection"], row["label"])
            if key in out:
                raise SliceSourceError(f"field_tiers.csv: duplicate tag for {key}")
            if row["min_tier"] not in TIERS:
                raise SliceSourceError(f"field_tiers.csv: {key} has unknown tier {row['min_tier']!r}")
            out[key] = row["min_tier"]
    return out


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    fields = load_merged(src)
    tiers = load_tiers(src)
    missing = sorted(set(fields) - set(tiers))
    orphan = sorted(set(tiers) - set(fields))
    if missing or orphan:
        raise SliceSourceError(f"field_tiers.csv out of step with the catalog: untagged {missing[:5]}, orphan {orphan[:5]}")
    rows = []
    for seq, (key, row) in enumerate(fields.items()):
        cells = []
        for c in FIELDS:
            v = row.get(c)
            if v is not None and not isinstance(v, str):
                raise SliceSourceError(f"schema field {key}: non-text cell {c}")
            cells.append(v)
        rows.append((seq, *cells, tiers[key]))
    return {"schema_field": (["seq", *FIELDS, "min_tier"], rows)}
