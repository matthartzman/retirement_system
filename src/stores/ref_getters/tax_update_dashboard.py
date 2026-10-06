"""Tax-update dashboard rows from ``reference.db`` (WP3.1 demonstration slice).

Table ``tax_update_status`` (built by ``tools/reference_slices/tax_update_dashboard.py``).
The getter reproduces the rows ``governance.tax_law_dashboard`` reads from
``reference_data/tax_update_dashboard.csv`` before its staleness overlay: every
field a ``str`` in CSV column order, ``blocking`` a ``bool``, rows in file order.
``governance`` is switched over in WP3.5; until then nothing in the product calls this.
"""
from __future__ import annotations

from typing import Any

from ..ref_data import RefData
from ..ref_access import reference

TABLE = "tax_update_status"
FIELDS = ("constant", "category", "year", "source", "source_url", "last_reviewed",
          "review_frequency", "status", "blocking", "notes")


def tax_update_dashboard(ref: RefData | None = None) -> list[dict[str, Any]]:
    """Fresh list of dashboard row dicts (callers may mutate them)."""
    ref = reference() if ref is None else ref
    cols = ", ".join(f'"{c}"' for c in FIELDS)
    rows = []
    for r in ref.query(f'SELECT {cols} FROM "{TABLE}" ORDER BY seq'):
        row = {c: r[c] for c in FIELDS}
        row["blocking"] = bool(row["blocking"])
        rows.append(row)
    return rows
