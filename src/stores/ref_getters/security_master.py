"""Security master rows from ``reference.db`` (WP3.6).

Table ``security_master`` (built by ``tools/reference_slices/security_master.py``).
``security_master_rows`` returns fresh ``dict`` rows in file order, every value a
``str`` (the old ``csv.DictReader`` shape); callers normalize as they always did.
"""
from __future__ import annotations

from ..ref_access import reference
from ..ref_data import RefData

COLUMNS = ("symbol", "asset_class", "sleeve", "region", "style", "notes")


def security_master_rows(ref: RefData | None = None) -> list[dict[str, str]]:
    ref = reference() if ref is None else ref
    sel = ", ".join(f'"{c}"' for c in COLUMNS)
    return [{c: r[c] for c in COLUMNS} for r in ref.query(f'SELECT {sel} FROM "security_master" ORDER BY seq')]
