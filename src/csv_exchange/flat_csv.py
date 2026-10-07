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


def dataset_csv_text(repo) -> str:
    """A flat plan dataset (``store.holdings`` ...) as the legacy CSV: header line, then one
    line per row, cells exactly as stored."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(repo.columns)
    for r in repo.rows():
        w.writerow([r[c] for c in repo.columns])
    return buf.getvalue()


def replace_dataset_from_csv_text(repo, text: str) -> int:
    """Replace a flat plan dataset from CSV text (UTF-8 BOM ignored, missing columns empty,
    extra columns dropped, fully blank lines skipped, cells kept unstripped)."""
    rows = []
    for raw in csv.DictReader(io.StringIO((text or "").lstrip("\ufeff"))):
        row = {c: (raw.get(c) or "") for c in repo.columns}
        if any(v.strip() for v in row.values()):
            rows.append(row)
    return repo.replace_all(rows)
