"""Generic engine for backfilling canonical Plan Data rows (system review item A7, Wave 3
item 3.12; on ``plan_rows`` since WP4.4c).

``src/server/app_core.py`` holds a declarative table of ``BackfillEntry(rows, anchor)``: the
canonical rows the guided UI depends on (newer controls an older plan predates) and where each
group goes inside its section. :func:`apply_backfill` makes the active plan's rows hold every
one of them: a row whose key ``(section, subsection, label)`` the plan already holds is never
touched (a user's value is never overwritten), a missing one is inserted into its section at
the entry's anchor.

It works on an open ``PlanStore`` inside the caller's transaction (``app_core`` runs it in the
active-plan edit context, which writes the new keys back into the CSV working copy while that
exists) and takes no file paths, except ``source_dir``: a row source may be a callable
``f(source_dir) -> rows`` for rows that depend on the holdings file (one per account), which
stays a file until its own dataset moves.

Anchors act on the rows of the section being inserted into, in display order, so an entry's
rows land at the same place relative to their neighbours as the CSV splice put them, minus the
position across other sections (``plan_rows`` sections have no file order).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional, Sequence, Union

Row = list  # [section, subsection, label, value, units, notes]
PlanRow = dict[str, Any]
# A callable row source takes ``source_dir`` (what :func:`apply_backfill` was given), so a
# dynamic entry (e.g. "one row per holdings account") reads from the same place the whole batch
# resolves its inputs from.
RowSource = Union[Sequence[Row], Callable[[Path], Sequence[Row]]]
# Anchor: the rows of the target section (display order) -> insert index, or None for the end.
Anchor = Callable[[Sequence[PlanRow]], Optional[int]]


def before_first(predicate: Callable[[PlanRow], bool]) -> Anchor:
    """Insert immediately before the first section row matching ``predicate``, else at the end."""
    def anchor(rows: Sequence[PlanRow]) -> Optional[int]:
        return next((i for i, r in enumerate(rows) if predicate(r)), None)
    return anchor


def after_last(predicate: Callable[[PlanRow], bool]) -> Anchor:
    """Insert immediately after the LAST section row matching ``predicate`` (scans every row,
    so a whole same-subsection block is passed, not just its first row), else at the end."""
    def anchor(rows: Sequence[PlanRow]) -> Optional[int]:
        last = None
        for i, r in enumerate(rows):
            if predicate(r):
                last = i + 1
        return last
    return anchor


def subsection_is(*subsections: str) -> Callable[[PlanRow], bool]:
    """Row predicate: the subsection is one of ``subsections``."""
    wanted = set(subsections)
    return lambda row: row["subsection"] in wanted


def label_is(label: str) -> Callable[[PlanRow], bool]:
    """Row predicate: the label equals ``label``."""
    return lambda row: row["label"] == label


class BackfillEntry(NamedTuple):
    rows: RowSource
    anchor: Optional[Anchor] = None  # None = always the end of the section


def insert_rows_at(store: Any, section: str, rows: Sequence[Row], at: Optional[int]) -> None:
    """Insert ``[section, subsection, label, value, units, notes]`` rows (all of ``section``) at
    index ``at`` of the section's display order (``None``: at the end). With ``at`` the section's
    ``sort_order`` is renumbered so the new rows sit exactly there (not a field the CSV
    write-back keys on)."""
    if at is not None:
        for i, r in enumerate(store.rows(section)):
            order = i if i < at else i + len(rows)
            if r["sort_order"] != order:
                store.set_row(r["row_id"], sort_order=order)
    for j, (_section, subsection, label, value, units, notes) in enumerate(rows):
        store.insert_row(section, subsection=subsection, label=label, value=value, units=units, notes=notes,
                         sort_order=None if at is None else at + j)


def _cells(row: Row) -> tuple[str, str, str, str, str, str]:
    cols = [str(c or "").strip() for c in row] + [""] * 6
    return cols[0], cols[1], cols[2], cols[3], cols[4], cols[5]


def pending_rows(store: Any, entries: Sequence[BackfillEntry], source_dir: Path | None = None
                 ) -> list[tuple[BackfillEntry, list[Row]]]:
    """The rows each entry would add (``[(entry, missing rows)]``, entries with none left out),
    without changing the plan. A key an earlier entry adds is not added again by a later one."""
    seen = {(r["section"], r["subsection"], r["label"]) for r in store.all_rows()}
    out: list[tuple[BackfillEntry, list[Row]]] = []
    for entry in entries:
        candidates = entry.rows(source_dir) if callable(entry.rows) else entry.rows
        missing: list[Row] = []
        for row in candidates:
            cells = _cells(row)
            if cells[:3] not in seen:
                seen.add(cells[:3])
                missing.append(list(cells))
        if missing:
            out.append((entry, missing))
    return out


def apply_backfill(store: Any, entries: Sequence[BackfillEntry], source_dir: Path | None = None) -> int:
    """Insert every missing canonical row into ``store`` (call inside its transaction); return
    how many were added.

    Entries apply in the order given against the growing rows, so a later entry's anchor sees an
    earlier entry's insertions, and an entry whose rows span sections (Model Constants and
    Withdrawal Policy) inserts each section's rows as one group at the anchor."""
    added = 0
    for entry, missing in pending_rows(store, entries, source_dir):
        by_section: dict[str, list[Row]] = {}
        for row in missing:
            by_section.setdefault(row[0], []).append(row)
        for section, rows in by_section.items():
            at = entry.anchor(store.rows(section)) if entry.anchor is not None else None
            insert_rows_at(store, section, rows, at)
            added += len(rows)
    return added
