"""Shared source readers for slice builders (strict: a source that changed shape fails the build)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence


class SliceSourceError(ValueError):
    """A reference source file is missing or not in the shape its slice expects."""


def read_csv(path: Path, header: Sequence[str]) -> list[dict[str, str]]:
    """Rows of a UTF-8 (optionally BOM) CSV as str dicts, in file order.

    Same reading semantics as the old ``csv.DictReader`` loaders, but the header
    must equal ``header`` exactly and every row must have exactly that many cells.
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != tuple(header):
            raise SliceSourceError(f"{path.name}: header {reader.fieldnames} != expected {list(header)}")
        rows = [dict(r) for r in reader]
    for i, r in enumerate(rows, 2):
        if None in r or any(v is None for v in r.values()):
            raise SliceSourceError(f"{path.name}:{i}: row does not have exactly {len(header)} cells")
    return rows
