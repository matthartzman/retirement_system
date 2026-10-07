"""Monarch field map from ``reference.db`` (WP3.8).

Table: ``monarch_field_map`` (built by ``tools/reference_slices/monarch_field_map.py``).

``monarch_field_map_data(ref=None)`` returns the field map dict, matching the old
``src.monarch_import.load_field_map()`` output exactly.
"""
from __future__ import annotations

import json

from ..ref_access import reference
from ..ref_data import RefData


def monarch_field_map_data(ref: RefData | None = None) -> dict[str, str]:
    """Load the Monarch column-name mapping from the reference database.

    Returns the same dict[str, str] structure as the old
    src.monarch_import.load_field_map(), fresh on every call.
    """
    ref = reference() if ref is None else ref
    rows = ref.query('SELECT data FROM "monarch_field_map" LIMIT 1')

    if not rows:
        # Should not happen if the database was built correctly, but provide sensible fallback
        return {
            "id_column": "id",
            "date_column": "date",
            "merchant_column": "merchant",
            "category_column": "category",
            "account_column": "account",
            "original_statement_column": "original_statement",
            "notes_column": "notes",
            "amount_column": "amount",
            "tags_column": "tags",
            "owner_column": "owner",
            "run_id_column": "run_id",
        }

    return json.loads(rows[0]["data"])
