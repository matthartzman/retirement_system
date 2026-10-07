"""The plan CSV set -> ``plan_rows`` (WP4.1 minimal importer; design F sections 4, 6, decision 7).

The *plan CSV set* is the legacy sectioned layout: the ``client_data.csv`` anchor plus nine
part files (``PLAN_CSV_FILES``), each a header ``section,subsection,label,value,units,notes``
(the optimizer-controls file calls its fifth column ``type``) followed by records. The
importer reads the set in ``PLAN_CSV_FILES`` order and writes one ``plan_rows`` row per data
row into an empty plan, in one transaction. Rules:

* Columns are found by header NAME, as the legacy ``csv.DictReader`` readers did
  (``data_io.load_csv`` / ``config_backend.load_csv``): any column order, extra columns
  ignored, names compared stripped and case-insensitively. ``section`` and ``label`` must be
  present, else the file is not a plan CSV; a missing ``subsection`` / ``value`` column reads
  as empty. The units column is ``units``, ``unit`` or ``type``; the notes column ``notes`` or
  ``note``. Cells are stripped. When the notes column is the header's last column, cells past
  it are an unquoted comma inside the notes text and are joined back onto ``notes`` with ``,``.
* A year-stamped label (``annual_spending_2026``) is stored under its canonical name
  (``annual_spending_base_year``): the rule every CSV reader applied at load time.
* A record is *blank* (all cells empty), a *comment* (first non-empty cell starts with
  ``#``), *data* (a section and a label), or *skipped* (anything else, e.g. a section without
  a label; listed in the report).
* Decision 7: a comment block directly above a data row (no blank or skipped record between)
  is appended to that row's ``notes`` (``#`` and ``--``/``==`` rule ends removed, lines joined
  with a space, ``"; "`` before existing notes) unless the data row is the file's first, i.e.
  the comment is the file's opening header block. Every other comment is dropped and
  counted; decoration-only lines (``# =====``) are dropped.
* Duplicate keys collapse as ``load_csv`` did (the last row wins): one row per
  ``(section, subsection, label)`` keeps the position of the first occurrence and the value,
  units and notes of the last, so a stale copy can never resurface after the effective row is
  deleted or edited (``collapse_duplicate_keys``; the anchor ``client_data.csv`` repeats some
  ``client_policy.csv`` Scenarios rows). ``sort_order`` counts per section in read order and
  row ids are allocated in read order, so ``PlanStore.sectioned_data()`` reproduces
  ``load_csv`` over the same files exactly.
* No legacy renames: those are conversion step C3 (``src/legacy_conversion``).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..plan_label_rules import canonical_label, dropped_at_load

# The plan CSV set, in read order (anchor first). Equals
# plan_data_registry.client_data_csv_files() (the layout ``data_io.load_csv`` still reads for
# the golden tool and tests).
PLAN_CSV_FILES: tuple[str, ...] = (
    "client_data.csv",
    "client_household.csv",
    "client_income.csv",
    "client_spending.csv",
    "client_assets.csv",
    "client_policy.csv",
    "client_insurance_estate.csv",
    "client_business.csv",
    "client_optional_functions.csv",
    "asset_class_optimizer_controls.csv",
)

# Old part file -> the sections it held (the shipped templates and fixtures). A section in
# more than one file was split by subsection or row; its first file is its *primary* file,
# which is where the legacy writers put new rows of that section (the old
# app_core _client_section_path searched the parts in this order). The anchor held only duplicates
# of Scenarios rows that client_policy.csv also carries.
PART_FILE_SECTIONS: dict[str, tuple[str, ...]] = {
    "client_household.csv": ("Household", "Economic Assumptions", "Payroll Tax", "Wellness",
                             "Social Security", "State Comparison"),
    "client_income.csv": ("Social Security", "Cashflow", "Income Streams"),
    "client_spending.csv": ("Cashflow", "Housing", "Wellness"),
    "client_assets.csv": ("Other Assets", "Liquidity Buffer", "HSA Policy", "Education Funding",
                          "Note Receivable", "DAF", "Hybrid LTC", "Positions"),
    "client_policy.csv": ("HSA Policy", "Account Policy", "HELOC", "Asset Allocation Policy",
                          "Asset Class Assumptions", "Model Constants", "Withdrawal Policy",
                          "Forced Actions", "Scenarios", "Reporting"),
    "client_insurance_estate.csv": ("Education Funding", "Annuity Death Benefits", "Estate Planning",
                                    "Insurance In Force", "Equity Compensation"),
    "client_business.csv": ("Business Succession",),
    "client_optional_functions.csv": ("Optional Functions",),
    "asset_class_optimizer_controls.csv": ("Asset Class Optimizer Controls",),
}
ANCHOR_FILE = "client_data.csv"

_REQUIRED_COLUMNS = ("section", "label")
_UNITS_COLUMNS = ("units", "unit", "type")
_NOTES_COLUMNS = ("notes", "note")
_REPEATED_HEADER = ("section", "subsection", "label")
_HEADER = ("section", "subsection", "label", "value", "units", "notes")
Key = tuple[str, str, str]  # (section, subsection, label): a plan row's identity

_ALNUM = re.compile(r"[A-Za-z0-9]")
_RULE_ENDS = re.compile(r"^[-=]{2,}\s*|\s*[-=]{2,}$")


class PlanCsvError(ValueError):
    """A file is not a plan CSV, or the target plan is not empty. Nothing was written."""


@dataclass(frozen=True)
class PlanCsvRow:
    section: str
    subsection: str
    label: str
    value: str
    units: str
    notes: str
    source_file: str
    line: int

    def fields(self) -> dict[str, str]:
        """The ``plan_rows`` text fields (what ``PlanStore.insert_row`` takes)."""
        return {"subsection": self.subsection, "label": self.label, "value": self.value,
                "units": self.units, "notes": self.notes}


@dataclass(frozen=True)
class SkippedRecord:
    source_file: str
    line: int
    reason: str
    cells: tuple[str, ...]


@dataclass
class ImportReport:
    files_read: list[str] = field(default_factory=list)
    files_missing: list[str] = field(default_factory=list)
    rows: int = 0
    comments_attached: int = 0
    comments_dropped: int = 0
    duplicates_collapsed: int = 0
    skipped: list[SkippedRecord] = field(default_factory=list)

    def merge(self, other: "ImportReport") -> None:
        self.files_read += other.files_read
        self.files_missing += other.files_missing
        self.rows += other.rows
        self.comments_attached += other.comments_attached
        self.comments_dropped += other.comments_dropped
        self.duplicates_collapsed += other.duplicates_collapsed
        self.skipped += other.skipped

    def as_dict(self) -> dict[str, Any]:
        return {
            "files_read": list(self.files_read),
            "files_missing": list(self.files_missing),
            "rows": self.rows,
            "comments_attached": self.comments_attached,
            "comments_dropped": self.comments_dropped,
            "duplicates_collapsed": self.duplicates_collapsed,
            "skipped": [{"file": s.source_file, "line": s.line, "reason": s.reason} for s in self.skipped],
        }


@dataclass
class PlanCsvSet:
    rows: list[PlanCsvRow]
    report: ImportReport
    # file name -> the text read (``read_plan_csv_set`` only), so a caller that also needs
    # the raw file (the legacy ``client_files`` copy, WP4.2) does not read it twice.
    texts: dict[str, str] = field(default_factory=dict)
    # file name -> data rows the file held before duplicate keys were collapsed
    rows_by_file: dict[str, int] = field(default_factory=dict)


# ----------------------------------------------------------------------------- helpers
def part_file_for_section(section: str) -> str:
    """The part file a section's rows belong in (its primary file; the anchor if unknown)."""
    for name, sections in PART_FILE_SECTIONS.items():
        if section in sections:
            return name
    return ANCHOR_FILE


def _trim(cells: list[str]) -> list[str]:
    """Drop leading and trailing empty cells."""
    lo, hi = 0, len(cells)
    while lo < hi and not cells[lo].strip():
        lo += 1
    while hi > lo and not cells[hi - 1].strip():
        hi -= 1
    return cells[lo:hi]


def _comment_text(cells: list[str]) -> str:
    """A comment record's text without its ``#`` marker and ``--``/``==`` rule ends
    ('' for a decoration-only line)."""
    text = _RULE_ENDS.sub("", ",".join(_trim(cells)).strip().lstrip("#").strip())
    return text if _ALNUM.search(text) else ""


@dataclass(frozen=True)
class _Columns:
    """Where each field sits in a file's header (by NAME, as ``csv.DictReader`` found them)."""
    section: int
    subsection: int | None
    label: int
    value: int | None
    units: int | None
    notes: int | None
    notes_last: bool          # the notes column is the header's last named column

    def cell(self, raw: list[str], index: int | None) -> str:
        return raw[index].strip() if index is not None and index < len(raw) else ""

    def notes_text(self, raw: list[str]) -> str:
        if self.notes is None or self.notes >= len(raw):
            return ""
        if self.notes_last:   # unquoted commas in the notes text spill into extra cells
            return ",".join(_trim(list(raw[self.notes:]))).strip()
        return raw[self.notes].strip()


def _read_header(cells: list[str], source_file: str) -> _Columns:
    """Map a header row to column positions; a file without ``section`` and ``label`` columns
    is not a plan CSV. A repeated name resolves to its last column, as ``DictReader`` did."""
    index: dict[str, int] = {}
    for i, cell in enumerate(cells):
        name = cell.strip().lower()
        if name:
            index[name] = i
    if any(name not in index for name in _REQUIRED_COLUMNS):
        raise PlanCsvError(f"{source_file}: not a plan CSV (header {cells[:6]!r})")
    notes = next((index[n] for n in _NOTES_COLUMNS if n in index), None)
    last_named = max(index.values())
    return _Columns(
        section=index["section"], subsection=index.get("subsection"), label=index["label"],
        value=index.get("value"), units=next((index[n] for n in _UNITS_COLUMNS if n in index), None),
        notes=notes, notes_last=notes is not None and notes == last_named,
    )


def collapse_duplicate_keys(rows: Iterable[PlanCsvRow]) -> tuple[list[PlanCsvRow], int]:
    """One row per ``(section, subsection, label)``, as the legacy loader's last-wins dict gave.

    The surviving row sits where the key first occurred and carries the value, units, notes
    and source of the key's last occurrence. Returns ``(rows, number of rows collapsed)``.
    """
    last: dict[tuple[str, str, str], PlanCsvRow] = {}
    order: list[tuple[str, str, str]] = []
    total = 0
    for row in rows:
        key = (row.section, row.subsection, row.label)
        if key not in last:
            order.append(key)
        last[key] = row
        total += 1
    return [last[key] for key in order], total - len(order)


# ------------------------------------------------------------------------------- parse
def parse_plan_csv(text: str, source_file: str) -> PlanCsvSet:
    """Parse one plan CSV file's text (BOM tolerated) into data rows plus a report.

    Rows are returned as read, duplicate keys included; :func:`read_plan_csv_set` and the
    writers collapse them."""
    report = ImportReport(files_read=[source_file])
    rows: list[PlanCsvRow] = []
    reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    columns: _Columns | None = None
    pending: list[str] = []
    seen_data = False

    def drop_pending() -> None:
        report.comments_dropped += len(pending)
        pending.clear()

    for raw in reader:
        line = reader.line_num
        if columns is None:
            if not any(c.strip() for c in raw):
                continue
            columns = _read_header(raw, source_file)
            continue
        first = next((c.strip() for c in raw if c.strip()), "")
        if not first:
            drop_pending()
            continue
        if first.startswith("#"):
            comment = _comment_text(raw)
            if comment:
                pending.append(comment)
            else:
                report.comments_dropped += 1
            continue
        section = columns.cell(raw, columns.section)
        subsection = columns.cell(raw, columns.subsection)
        label = canonical_label(columns.cell(raw, columns.label))
        if [section.lower(), subsection.lower(), label.lower()] == list(_REPEATED_HEADER):
            reason = "repeated header"
        elif not section:
            reason = "no section"
        elif not label:
            reason = "no label"
        else:
            reason = ""
        if reason:
            report.skipped.append(SkippedRecord(source_file, line, reason, tuple(raw)))
            drop_pending()
            continue
        notes = columns.notes_text(raw)
        if pending and seen_data:
            joined = " ".join(pending)
            notes = f"{notes}; {joined}" if notes else joined
            report.comments_attached += len(pending)
            pending.clear()
        else:
            drop_pending()
        seen_data = True
        rows.append(PlanCsvRow(section, subsection, label, columns.cell(raw, columns.value),
                               columns.cell(raw, columns.units), notes, source_file, line))
    drop_pending()
    report.rows = len(rows)
    return PlanCsvSet(rows, report)


def read_plan_csv_set(folder: str | Path, files: Iterable[str] = PLAN_CSV_FILES) -> PlanCsvSet:
    """Parse every present file of the set from ``folder``, in order. Missing files are listed."""
    root = Path(folder)
    out = PlanCsvSet([], ImportReport())
    for name in files:
        path = root / name
        if not path.is_file():
            out.report.files_missing.append(name)
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            text = handle.read()
        parsed = parse_plan_csv(text, name)
        out.texts[name] = text
        out.rows_by_file[name] = len(parsed.rows)
        out.rows += parsed.rows
        out.report.merge(parsed.report)
    out.rows, out.report.duplicates_collapsed = collapse_duplicate_keys(out.rows)
    out.report.rows = len(out.rows)
    return out


# ------------------------------------------------------------------------------- write
def write_plan_rows(store: Any, rows: Iterable[PlanCsvRow]) -> int:
    """Write rows, in order, into an empty plan (an open, writable ``PlanStore``).

    One transaction: on any error nothing is written. ``sort_order`` counts per section.
    A repeated key is written once (:func:`collapse_duplicate_keys`: first position, last
    value). Returns the number of rows written.
    """
    rows, _ = collapse_duplicate_keys(rows)
    count = 0
    with store.transaction():
        if store.sections():
            raise PlanCsvError("the target plan already has rows; import needs an empty plan")
        next_order: dict[str, int] = {}
        for row in rows:
            order = next_order.get(row.section, 0)
            next_order[row.section] = order + 1
            store.insert_row(row.section, sort_order=order, **row.fields())
            count += 1
    return count


def import_plan_csv_set(folder: str | Path, store: Any, files: Iterable[str] = PLAN_CSV_FILES, *,
                        drop_never_kept: bool = False) -> ImportReport:
    """Read the plan CSV set from ``folder`` and write it into the empty plan ``store``.

    ``drop_never_kept`` also drops the rows no plan keeps (``plan_label_rules.dropped_at_load``:
    ``label`` header rows and the retired ``Scenarios / Sell Home`` labels), as the old loader
    did at every load; the demo seed uses it."""
    parsed = read_plan_csv_set(folder, files)
    rows = [r for r in parsed.rows if not dropped_at_load(r.section, r.subsection, r.label)] if drop_never_kept else parsed.rows
    parsed.report.rows = write_plan_rows(store, rows)
    return parsed.report
