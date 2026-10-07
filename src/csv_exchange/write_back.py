"""Write ``plan_rows`` edits back into the plan CSV set (WP4.3 transition).

The grid (``/api/config/rows``) and ``/api/plan/forms`` write ``plan_rows``. Until the
remaining CSV writers move to the rows (WP4.4 strategy endpoints and ``_replace_*``, WP4.5
feature backfill, P3.5 whole-set writers), those writers read and rewrite the CSV set and
the CSV-to-rows bridge (``active_plan.sync_active_plan_from_csv``) carries the set into the
rows. So a row-store edit must also land in the CSV set, or the next bridge run would put
the old value back and the next CSV writer would never see it.
:func:`write_back_rows` computes that CSV change. It is pure: texts in, texts out.

What it changes, and only for the ``touched`` keys:

* a deleted key: every record of the key is removed, with the ``#`` comment block directly
  above it when that block was attached to it (decision 7: the comment lives on in the
  row's notes, so it goes with the row);
* a new key: one record directly after the last record of its section in the set (rows are
  appended at the end of their section), or at the end of the section's primary part file
  (``part_file_for_section``) for a new section;
* a changed value: the value cell of every record of the key.

Then every row of the set must read back as the plan has it (``parse_plan_csv`` rules,
duplicate keys collapsed, the load-time drops of ``plan_label_rules.dropped_at_load``). A
row whose units or notes no longer read back (a removed comment row can move another
comment's attachment) gets explicit cells and loses the comment rows above it. Anything
else that does not read back (an untouched value, a missing or extra key, the order of
rows inside a section) raises :class:`PlanCsvError` and nothing is written: the edit fails
instead of being lost on the next bridge run. Section order is not checked; a new section
the CSV set places elsewhere makes the next bridge run renumber the rows (``sync_plan_rows``
rewrites on a section-order change).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..plan_label_rules import canonical_label, dropped_at_load
from .plan_csv import (
    PLAN_CSV_FILES,
    Key,
    PlanCsvError,
    _Columns,
    _HEADER,
    _REPEATED_HEADER,
    _read_header,
    collapse_duplicate_keys,
    parse_plan_csv,
    part_file_for_section,
)



@dataclass
class _File:
    name: str
    records: list[list[str]]
    columns: _Columns | None = None
    header_at: int = -1
    dirty: bool = False

    @classmethod
    def parse(cls, name: str, text: str) -> "_File":
        records = [list(r) for r in csv.reader(io.StringIO(text.removeprefix("﻿"), newline=""))]
        out = cls(name, records)
        for i, raw in enumerate(records):
            if any(c.strip() for c in raw):
                out.columns, out.header_at = _read_header(raw, name), i
                break
        return out

    def ensure_header(self) -> None:
        if self.columns is None:
            self.records.append(list(_HEADER))
            self.header_at = len(self.records) - 1
            self.columns = _read_header(self.records[-1], self.name)
            self.dirty = True

    def text(self) -> str:
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\n").writerows(self.records)
        return buf.getvalue()

    # ------------------------------------------------------------------ records
    @staticmethod
    def is_comment(raw: list[str]) -> bool:
        first = next((c.strip() for c in raw if c.strip()), "")
        return first.startswith("#")

    def key(self, i: int) -> Key | None:
        """The key of record ``i`` when it is a data record (as ``parse_plan_csv`` reads it)."""
        cols, raw = self.columns, self.records[i]
        if cols is None or i <= self.header_at or self.is_comment(raw) or not any(c.strip() for c in raw):
            return None
        section, subsection = cols.cell(raw, cols.section), cols.cell(raw, cols.subsection)
        label = canonical_label(cols.cell(raw, cols.label))
        if not section or not label or (section.lower(), subsection.lower(), label.lower()) == _REPEATED_HEADER:
            return None
        return (section, subsection, label)

    def data_records(self) -> list[tuple[int, Key]]:
        return [(i, k) for i in range(len(self.records)) if (k := self.key(i)) is not None]

    def comment_block_above(self, i: int) -> list[int]:
        """Indices of the comment records directly above record ``i``."""
        out: list[int] = []
        j = i - 1
        while j > self.header_at and self.is_comment(self.records[j]):
            out.append(j)
            j -= 1
        return out

    def set_cell(self, i: int, index: int | None, value: str, what: str) -> None:
        if index is None:
            if value:
                raise PlanCsvError(f"{self.name}: no {what} column to write {value!r} into")
            return
        raw = self.records[i]
        while len(raw) <= index:
            raw.append("")
        if raw[index] != value:
            raw[index] = value
            self.dirty = True

    def set_notes(self, i: int, notes: str) -> None:
        cols = self.columns
        if cols.notes_last and cols.notes is not None:  # drop unquoted-comma spill-over cells
            del self.records[i][cols.notes + 1:]
        self.set_cell(i, cols.notes, notes, "notes")

    def new_record(self, row: Mapping[str, Any]) -> list[str]:
        cols = self.columns
        width = max(i for i in (cols.section, cols.subsection, cols.label, cols.value, cols.units, cols.notes)
                    if i is not None) + 1
        raw = [""] * width
        for index, name in ((cols.section, "section"), (cols.subsection, "subsection"), (cols.label, "label"),
                            (cols.value, "value"), (cols.units, "units"), (cols.notes, "notes")):
            if index is not None:
                raw[index] = str(row.get(name, ""))
            elif str(row.get(name, "")):
                raise PlanCsvError(f"{self.name}: no {name} column to write {row.get(name)!r} into")
        return raw


@dataclass
class _Set:
    files: dict[str, _File] = field(default_factory=dict)

    def file(self, name: str) -> _File:
        if name not in self.files:
            self.files[name] = _File(name, [])
        return self.files[name]

    def ordered(self) -> list[_File]:
        names = [n for n in PLAN_CSV_FILES if n in self.files]
        return [self.files[n] for n in names + sorted(set(self.files) - set(names))]

    def occurrences(self) -> dict[Key, list[tuple[_File, int]]]:
        out: dict[Key, list[tuple[_File, int]]] = {}
        for f in self.ordered():
            for i, key in f.data_records():
                out.setdefault(key, []).append((f, i))
        return out

    def read_back(self) -> dict[Key, tuple[str, str, str]]:
        """What the bridge would store: key -> (value, units, notes), in read order."""
        rows = []
        for f in self.ordered():
            if f.columns is not None:
                rows += parse_plan_csv(f.text(), f.name).rows
        collapsed, _ = collapse_duplicate_keys(rows)
        return {(r.section, r.subsection, r.label): (r.value, r.units, r.notes)
                for r in collapsed if not dropped_at_load(r.section, r.subsection, r.label)}


def _fields(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("value", "")), str(row.get("units", "")), str(row.get("notes", "")))


def _by_section(keys: Iterable[Key]) -> dict[str, list[Key]]:
    out: dict[str, list[Key]] = {}
    for key in keys:
        out.setdefault(key[0], []).append(key)
    return out


def write_back_rows(texts: Mapping[str, str], rows: Sequence[Mapping[str, Any]],
                    touched: Iterable[Key]) -> dict[str, str]:
    """The plan CSV set after writing the ``touched`` keys of ``rows`` back into it.

    ``texts``: file name -> current text, for the plan CSV files that exist. ``rows``: every
    plan row after the edit (dicts with ``section``, ``subsection``, ``label``, ``value``,
    ``units``, ``notes``), each section's rows in display order. ``touched``: the keys the
    edit set, inserted or deleted. Returns ``{file name: new text}`` for the files that
    change. Raises :class:`PlanCsvError` when the result would not read back as ``rows``.
    """
    want: dict[Key, tuple[str, str, str]] = {}
    for row in rows:
        key = (str(row["section"]), str(row["subsection"]), str(row["label"]))
        if not dropped_at_load(*key):
            want[key] = _fields(row)  # a repeated key: first position, last fields (as read)
    touched = set(touched)
    plan = _Set({name: _File.parse(name, text) for name, text in texts.items()})

    # 1. deleted keys: their records, and the comment block each one carried in its notes
    for f in plan.ordered():
        drop: set[int] = set()
        seen_data = False
        for i, key in f.data_records():
            if key in touched and key not in want:
                drop.add(i)
                if seen_data:
                    drop.update(f.comment_block_above(i))
            seen_data = True
        if drop:
            f.records = [r for i, r in enumerate(f.records) if i not in drop]
            f.dirty = True

    # 2. new keys, in display order: after the last record of their section, else at the end
    #    of the section's primary file
    present = set(plan.occurrences())
    for key in [k for k in want if k in touched and k not in present]:
        row = dict(zip(("section", "subsection", "label"), key))
        row.update(zip(("value", "units", "notes"), want[key]))
        last: tuple[_File, int] | None = None
        for f in plan.ordered():
            for i, k in f.data_records():
                if k[0] == key[0]:
                    last = (f, i)
        if last is not None:
            f, i = last
            f.records.insert(i + 1, f.new_record(row))
        else:
            f = plan.file(part_file_for_section(key[0]))
            f.ensure_header()
            if f.records and f.is_comment(f.records[-1]):
                f.records.append([])  # a comment block must not attach to the new row
            f.records.append(f.new_record(row))
        f.dirty = True

    # 3. values of touched keys; units and notes of any row that no longer reads back
    occurrences = plan.occurrences()
    for key, (value, units, notes) in want.items():
        if key in touched:
            for f, i in occurrences.get(key, []):
                f.set_cell(i, f.columns.value, value, "value")
    got = plan.read_back()
    for key, (value, units, notes) in want.items():
        if key in got and got[key][1:] != (units, notes):
            f, i = plan.occurrences()[key][-1]
            above = f.comment_block_above(i)
            if above:
                f.records = [r for j, r in enumerate(f.records) if j not in set(above)]
                f.dirty = True
                i -= len(above)
            f.set_cell(i, f.columns.units, units, "units")
            f.set_notes(i, notes)

    # 4. the whole set must read back as the plan
    got = plan.read_back()
    if got != want:
        missing = [k for k in want if k not in got]
        extra = [k for k in got if k not in want]
        differ = [k for k in want if k in got and got[k] != want[k]]
        raise PlanCsvError(
            "writing the plan rows back to the plan CSV set would not read back the same "
            f"(missing {missing[:3]}, extra {extra[:3]}, different {differ[:3]})")
    want_order, got_order = _by_section(want), _by_section(got)
    bad = [s for s in want_order if want_order[s] != got_order.get(s)]
    if bad:
        raise PlanCsvError(f"writing the plan rows back would reorder rows of section(s) {bad[:3]}")
    return {f.name: f.text() for f in plan.ordered() if f.dirty}
