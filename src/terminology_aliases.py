from __future__ import annotations

"""Compatibility-safe terminology registry.

Canonical product language is healthcare-oriented.  Older internal CSV labels and
projection keys may still use ``wellness`` for backward compatibility.  This
module centralizes those aliases so future migrations can rename user-facing
surfaces without breaking saved plans, historical snapshots, or imported CSVs.
"""

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TerminologyAlias:
    canonical_id: str
    canonical_label: str
    legacy_ids: tuple[str, ...]
    notes: str = ""


HEALTHCARE_PREMIUM = TerminologyAlias(
    canonical_id="healthcare_premium",
    canonical_label="Healthcare Premium",
    legacy_ids=(
        "pre65_healthcare_premium",
        "medicare_part_b",
        "medicare_part_d",
        "medigap_premium",
        "medicare_part_g",
    ),
    notes="Includes Pre-65 Healthcare Premium and Medicare Parts B, D, and G/Medigap premiums.",
)

OOP_MEDICAL_CAP = TerminologyAlias(
    canonical_id="medical_oop_cap",
    canonical_label="Medical OOP Cap",
    legacy_ids=("annual_oop_max", "oop_max"),
    notes="Reference cap for non-premium medical spending; not a standalone expense row.",
)

TERMINOLOGY_ALIASES: tuple[TerminologyAlias, ...] = (HEALTHCARE_PREMIUM, OOP_MEDICAL_CAP)
_ALIAS_BY_ID = {alias.canonical_id: alias for alias in TERMINOLOGY_ALIASES}
for alias in TERMINOLOGY_ALIASES:
    for legacy in alias.legacy_ids:
        _ALIAS_BY_ID[legacy] = alias


def canonical_id(value: str) -> str:
    key = str(value or "").strip().lower()
    alias = _ALIAS_BY_ID.get(key)
    return alias.canonical_id if alias else key


def user_label(value: str) -> str:
    key = str(value or "").strip().lower()
    alias = _ALIAS_BY_ID.get(key)
    if alias:
        return alias.canonical_label
    return str(value or "")


def healthcare_alias_payload() -> dict:
    return {
        "schema": "terminology_aliases_v1",
        "aliases": [
            {
                "canonical_id": alias.canonical_id,
                "canonical_label": alias.canonical_label,
                "legacy_ids": list(alias.legacy_ids),
                "notes": alias.notes,
            }
            for alias in TERMINOLOGY_ALIASES
        ],
    }
