"""Generic CSV text -> list of dict rows (a headed, flat table), for the one-time converter.

The plan CSV set has its own reader (``plan_csv``: sections, comments, notes); this is the
plain ``csv.DictReader`` shape the legacy custom reference files (capital-market assumptions,
asset correlations, real-loss curves) used. Cells are stripped; fully empty rows are skipped.
"""
from __future__ import annotations

import csv
import io


def parse_csv_dicts(text: str) -> list[dict[str, str]]:
    """The data rows of a headed CSV text as ``{column: stripped text}`` dicts, in order."""
    out: list[dict[str, str]] = []
    for row in csv.DictReader(io.StringIO((text or "").lstrip("﻿"))):
        clean = {str(k or "").strip(): str(v or "").strip() for k, v in row.items() if k is not None}
        if any(clean.values()):
            out.append(clean)
    return out
