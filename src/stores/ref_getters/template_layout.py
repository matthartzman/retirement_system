"""Workbook template layout from ``reference.db`` (WP3.8).

Table: ``template_layout`` (built by ``tools/reference_slices/template_layout.py``).

``template_layout_data(ref=None)`` returns the layout dict, matching the old
``src.reporting.workbook_common._load_template_layout()`` output exactly.
"""
from __future__ import annotations

import json

from ..ref_access import reference
from ..ref_data import RefData


def template_layout_data(ref: RefData | None = None) -> dict:
    """Load the workbook template layout from the reference database.

    Returns the same dict structure as the old
    src.reporting.workbook_common._load_template_layout(), fresh on every call.
    The dict maps sheet names to col/row layout dicts.
    """
    ref = reference() if ref is None else ref
    rows = ref.query('SELECT data FROM "template_layout" LIMIT 1')

    if not rows:
        # Should not happen if the database was built correctly, but provide empty fallback
        return {}

    return json.loads(rows[0]["data"])
