"""Generic CSV text -> list of dict rows (a headed, flat table), for the one-time converter.

The plan CSV set has its own reader (``plan_csv``: sections, comments, notes); this is the
plain ``csv.DictReader`` shape the legacy custom reference files (capital-market assumptions,
asset correlations, real-loss curves) used. Cells are stripped; fully empty rows are skipped.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Iterable, Mapping


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
    header = [*repo.columns, *repo.extra_columns()]
    w.writerow(header)
    for r in repo.rows():
        w.writerow([r.get(c, "") for c in header])
    return buf.getvalue()


def dataset_rows_from_csv_text(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """``(header, rows)`` of a flat dataset CSV text as the dataset tables take it: UTF-8 BOM
    ignored, cells kept unstripped, fully blank lines skipped."""
    reader = csv.DictReader(io.StringIO((text or "").lstrip("\ufeff")))
    header = [str(c) for c in (reader.fieldnames or []) if c is not None and str(c)]
    rows = []
    for raw in reader:
        row = {str(k): (v or "") for k, v in raw.items() if k is not None and str(k)}
        if any(v.strip() for v in row.values()):
            rows.append(row)
    return header, rows


def read_dataset_csv_file(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    """:func:`dataset_rows_from_csv_text` of a legacy file, decoded the way the old spending
    readers decoded it (UTF-8, undecodable bytes replaced, NUL bytes dropped)."""
    text = Path(path).read_bytes().decode("utf-8-sig", errors="replace").replace("\x00", "")
    return dataset_rows_from_csv_text(text)


def replace_dataset_from_csv_text(repo, text: str) -> int:
    """Replace a flat plan dataset from CSV text (UTF-8 BOM ignored, missing columns empty,
    other columns kept as extra columns, fully blank lines skipped, cells kept unstripped)."""
    _, rows = dataset_rows_from_csv_text(text)
    for row in rows:
        for c in repo.columns:
            row.setdefault(c, "")
    return repo.replace_all(rows)


# Plan dataset name (``PlanStore.dataset(name)``) -> its legacy CSV file name.
FLAT_DATASET_FILES: dict[str, str] = {
    "holdings": "client_holdings.csv",
    "liabilities": "client_liabilities.csv",
    "hsa_schedule": "client_hsa_schedule.csv",
    "target_allocation": "target_allocation.csv",
    # The spending set (``store.spending``); WP6.3b/c add budget, lines, overrides, rules, map.
    "spending_taxonomy": "client_spending_taxonomy.csv",
    "spending_aliases": "client_spending_aliases.csv",
}


def import_flat_datasets(folder: str | Path, store: Any, names: Iterable[str] | None = None) -> dict[str, int]:
    """Load the flat dataset CSVs found in ``folder`` into the plan's dataset tables
    (``{dataset: rows written}``; a missing file leaves its table as it is). One transaction."""
    wanted = list(FLAT_DATASET_FILES if names is None else names)
    out: dict[str, int] = {}
    with store.transaction():
        for name in wanted:
            path = Path(folder) / FLAT_DATASET_FILES[name]
            if path.is_file():
                out[name] = replace_dataset_from_csv_text(store.dataset(name), path.read_text(encoding="utf-8-sig"))
    return out


def import_flat_dataset_texts(store: Any, texts: Mapping[str, str]) -> dict[str, int]:
    """Same as :func:`import_flat_datasets` for CSV text already read (``{dataset: text}``)."""
    with store.transaction():
        return {n: replace_dataset_from_csv_text(store.dataset(n), t) for n, t in texts.items() if n in FLAT_DATASET_FILES}
