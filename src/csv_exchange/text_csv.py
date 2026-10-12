"""Raw CSV text <-> rows helpers for adapters outside csv_exchange (WP9.3).

Unlike ``flat_csv.parse_csv_dicts`` these do no stripping or blank-row skipping: they are the
exact ``csv.DictReader`` / ``csv.reader`` / ``csv.writer`` behaviour the adapters used inline,
so moving the call here cannot move a number.
"""
from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence


def dict_reader(text: str | None) -> csv.DictReader:
    """``csv.DictReader`` over CSV text (``None`` reads as empty)."""
    return csv.DictReader(io.StringIO(text or ""))


def dict_reader_stream(stream) -> csv.DictReader:
    """``csv.DictReader`` over an already-open text stream (file adapters only)."""
    return csv.DictReader(stream)


def list_rows(text: str | None) -> list[list[str]]:
    """Every row of a CSV text as a list of cells (``csv.reader``)."""
    return list(csv.reader(io.StringIO(text or "")))


def list_rows_stream(stream) -> list[list[str]]:
    return list(csv.reader(stream))


def rows_to_text(rows: Iterable[Sequence[object]], *, lineterminator: str = "\n") -> str:
    """CSV text for rows of cells (``csv.writer``)."""
    out = io.StringIO()
    csv.writer(out, lineterminator=lineterminator).writerows(rows)
    return out.getvalue()


def write_rows_stream(stream, rows: Iterable[Sequence[object]], *, lineterminator: str = "\n") -> None:
    csv.writer(stream, lineterminator=lineterminator).writerows(rows)
