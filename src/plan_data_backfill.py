"""Generic engine for backfilling canonical Plan Data CSV rows (system review
item A7, Wave 3 item 3.12).

src/server/app_core.py had ~12 near-identical ``_ensure_*_ui_plan_data_rows``
functions, each repeating the same five-step body with a different row table
and anchor: read a CSV, compute which canonical rows are missing, find an
insertion point, splice the missing rows in, write back. One row-key
collision across targets meant the same file could be read and rewritten up
to five times per orchestrator call.

This module is the batched engine those functions now call into: a
declarative ``BackfillEntry(file_name, rows, anchor)`` table, applied with one
read and one write per distinct file no matter how many entries target it.

It takes an explicit target directory rather than resolving workspace/session
state itself (the caller's job), which is what makes it testable against a
plain ``tmp_path`` with no pytest guard — the guard on the orchestrator
existed solely because the original always resolved to the live input/
directory, and every test mocked around it rather than exercising it.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, NamedTuple, Optional, Sequence, Union

Row = list
# A callable row source takes the same target_dir apply_backfill was given,
# so a dynamic entry (e.g. "one row per holdings account") reads from the
# same injected directory everything else in the batch writes to, rather
# than reaching into module-level workspace state of its own.
RowSource = Union[Sequence[Row], Callable[[Path], Sequence[Row]]]
Anchor = Callable[[Sequence[Row]], int]


def insert_before(predicate: Callable[[Row], bool]) -> Anchor:
    """Insert immediately before the first existing row matching ``predicate``
    (scanning rows after the header), or at the end if nothing matches."""
    def anchor(rows: Sequence[Row]) -> int:
        for i, row in enumerate(rows[1:], start=1):
            if predicate(row):
                return i
        return len(rows)
    return anchor


def insert_after_last(predicate: Callable[[Row], bool]) -> Anchor:
    """Insert immediately after the LAST existing row matching ``predicate``
    — scans every row (does not stop at the first match) — or at the end if
    nothing matches. Matches the original ``_ensure_row_in_csv`` behavior of
    landing after a whole same-(section, subsection) block rather than
    before its first row."""
    def anchor(rows: Sequence[Row]) -> int:
        insert_at = len(rows)
        for i, row in enumerate(rows[1:], start=1):
            if predicate(row):
                insert_at = i + 1
        return insert_at
    return anchor


def section_is(*sections: str) -> Callable[[Row], bool]:
    """Row predicate: column 0 (section) is one of ``sections``."""
    wanted = set(sections)
    return lambda row: str(row[0] if row else "").strip() in wanted


def section_subsection_is(section: str, subsection: str) -> Callable[[Row], bool]:
    """Row predicate: columns 0/1 (section, subsection) match exactly."""
    def predicate(row: Row) -> bool:
        sec = str(row[0] if row else "").strip()
        sub = str(row[1] if len(row) > 1 else "").strip()
        return sec == section and sub == subsection
    return predicate


class BackfillEntry(NamedTuple):
    file_name: str
    rows: RowSource
    anchor: Optional[Anchor] = None  # None = always append at end


def ensure_header(rows: list[Row]) -> list[Row]:
    header = ["section", "subsection", "label", "value", "units", "notes"]
    if not rows:
        return [header]
    first = [str(x or "").strip().lower() for x in rows[0][:3]]
    if first[:3] != ["section", "subsection", "label"]:
        return [header, *rows]
    while len(rows[0]) < 6:
        rows[0].append("")
    rows[0][:6] = header
    return rows


def row_key(row: Row) -> tuple[str, str, str]:
    cols = list(row) + [""] * 6
    return (str(cols[0]).strip(), str(cols[1]).strip(), str(cols[2]).strip())


def _read_rows(path: Path) -> list[Row]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def _write_rows(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    tmp.replace(path)


def apply_backfill(target_dir: Path, entries: Sequence[BackfillEntry]) -> dict[str, int]:
    """Apply every entry against files in ``target_dir``.

    Batches to one read + one write per distinct file, however many entries
    target it, applying that file's entries in the order given against the
    growing in-memory row list — so a later entry's anchor sees an earlier
    entry's insertions, and a row already present (from an earlier entry or
    the file itself) is never duplicated. This is the same sequencing the
    original per-function read-modify-write calls produced, without the
    redundant disk round-trips (nothing changes for a file whose entries add
    no rows: it is read but never rewritten).

    Returns ``{file_name: rows_added}`` for files that actually changed.
    """
    by_file: dict[str, list[BackfillEntry]] = {}
    for entry in entries:
        by_file.setdefault(entry.file_name, []).append(entry)

    added_counts: dict[str, int] = {}
    for file_name, file_entries in by_file.items():
        path = target_dir / file_name
        rows = ensure_header(_read_rows(path))
        seen = {row_key(r) for r in rows[1:]}
        added = 0
        for entry in file_entries:
            candidates = entry.rows(target_dir) if callable(entry.rows) else entry.rows
            missing = [list(r) for r in candidates if row_key(r) not in seen]
            if not missing:
                continue
            insert_at = entry.anchor(rows) if entry.anchor is not None else len(rows)
            rows[insert_at:insert_at] = missing
            for r in missing:
                seen.add(row_key(r))
            added += len(missing)
        if added:
            _write_rows(path, rows)
            added_counts[file_name] = added
    return added_counts
