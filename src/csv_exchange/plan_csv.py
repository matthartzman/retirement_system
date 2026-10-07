"""The plan CSV set -> ``plan_rows`` (WP4.1 minimal importer; design F sections 4, 6, decision 7).

The *plan CSV set* is the legacy sectioned layout: the ``client_data.csv`` anchor plus nine
part files (``PLAN_CSV_FILES``), each a header ``section,subsection,label,value,units,notes``
(the optimizer-controls file calls its fifth column ``type``) followed by records. The
importer reads the set in ``PLAN_CSV_FILES`` order and writes one ``plan_rows`` row per data
row into an empty plan, in one transaction. Rules:

* Cells are read by position and stripped. Cells past the sixth are an unquoted comma inside
  the notes text and are joined back onto ``notes`` with ``,``.
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
* ``sort_order`` counts per section in read order and row ids are allocated in read order,
  so ``PlanStore.sectioned_data()`` reproduces ``load_csv`` over the same files exactly,
  duplicate keys included (the last one wins).
* No legacy renames: those are conversion step C3 (``src/legacy_conversion``).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# The plan CSV set, in read order (anchor first). Equals
# plan_data_registry.client_data_csv_files() until WP4.5 retires that registry.
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
# which is where the legacy writers put new rows of that section (app_core
# _client_section_path searched the parts in this order). The anchor held only duplicates
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

_HEADER = ("section", "subsection", "label", "value")
_FIFTH_COLUMN = ("units", "type")

# Year-stamped labels -> canonical names; the same table data_io / config_backend apply
# at load time (a test keeps them equal until WP4.2 deletes those loaders).
_YEAR_LABEL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^annual_401k_limit_\d{4}$"), "annual_401k_limit_base_year"),
    (re.compile(r"^annual_spending_\d{4}$"), "annual_spending_base_year"),
    (re.compile(r"^balance_\d{1,2}_\d{1,2}_\d{4}$"), "balance_as_of_plan_start"),
    (re.compile(r"^value_\d{1,2}_\d{1,2}_\d{4}$"), "value_as_of_plan_start"),
    (re.compile(r"^family_annual_limit_\d{4}$"), "family_annual_limit_base_year"),
    (re.compile(r"^self_only_annual_limit_\d{4}$"), "self_only_annual_limit_base_year"),
    (re.compile(r"^coverage_\d{4}_family_months$"), "coverage_base_year_family_months"),
    (re.compile(r"^coverage_\d{4}_self_only_months$"), "coverage_base_year_self_only_months"),
    (re.compile(r"^ss_wage_base_\d{4}$"), "ss_wage_base_base_year"),
    (re.compile(r"^ltcg_0pct_top_mfj_\d{4}$"), "ltcg_0pct_top_mfj_base_year"),
    (re.compile(r"^ltcg_15pct_top_mfj_\d{4}$"), "ltcg_15pct_top_mfj_base_year"),
    (re.compile(r"^part_b_premium_\d{4}$"), "part_b_base_premium_monthly"),
    (re.compile(r"^part_d_premium_\d{4}$"), "part_d_base_premium_monthly"),
    (re.compile(r"^annual_premium_\d{4}$"), "annual_premium_base_year"),
)
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
    skipped: list[SkippedRecord] = field(default_factory=list)

    def merge(self, other: "ImportReport") -> None:
        self.files_read += other.files_read
        self.files_missing += other.files_missing
        self.rows += other.rows
        self.comments_attached += other.comments_attached
        self.comments_dropped += other.comments_dropped
        self.skipped += other.skipped

    def as_dict(self) -> dict[str, Any]:
        return {
            "files_read": list(self.files_read),
            "files_missing": list(self.files_missing),
            "rows": self.rows,
            "comments_attached": self.comments_attached,
            "comments_dropped": self.comments_dropped,
            "skipped": [{"file": s.source_file, "line": s.line, "reason": s.reason} for s in self.skipped],
        }


@dataclass
class PlanCsvSet:
    rows: list[PlanCsvRow]
    report: ImportReport


# ----------------------------------------------------------------------------- helpers
def canonical_label(label: str) -> str:
    """Strip a label and map a year-stamped one to its canonical name."""
    text = (label or "").strip()
    for pattern, replacement in _YEAR_LABEL_PATTERNS:
        if pattern.match(text):
            return replacement
    return text


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


def _check_header(cells: list[str], source_file: str) -> None:
    head = [c.strip().lower() for c in cells[:6]]
    if tuple(head[:4]) != _HEADER or (len(head) > 4 and head[4] and head[4] not in _FIFTH_COLUMN) \
            or (len(head) > 5 and head[5] and head[5] != "notes"):
        raise PlanCsvError(f"{source_file}: not a plan CSV (header {cells[:6]!r})")


# ------------------------------------------------------------------------------- parse
def parse_plan_csv(text: str, source_file: str) -> PlanCsvSet:
    """Parse one plan CSV file's text (BOM tolerated) into data rows plus a report."""
    report = ImportReport(files_read=[source_file])
    rows: list[PlanCsvRow] = []
    reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    header_seen = False
    pending: list[str] = []
    seen_data = False

    def drop_pending() -> None:
        report.comments_dropped += len(pending)
        pending.clear()

    for raw in reader:
        line = reader.line_num
        if not header_seen:
            if not any(c.strip() for c in raw):
                continue
            _check_header(raw, source_file)
            header_seen = True
            continue
        cells = [c.strip() for c in raw] + [""] * (6 - len(raw))
        first = next((c for c in cells if c), "")
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
        section, subsection, label = cells[0], cells[1], canonical_label(cells[2])
        if [c.lower() for c in cells[:3]] == list(_HEADER[:3]):
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
        notes = ",".join(_trim(list(raw[5:]))).strip() if len(raw) > 5 else ""
        if pending and seen_data:
            joined = " ".join(pending)
            notes = f"{notes}; {joined}" if notes else joined
            report.comments_attached += len(pending)
            pending.clear()
        else:
            drop_pending()
        seen_data = True
        rows.append(PlanCsvRow(section, subsection, label, cells[3], cells[4], notes, source_file, line))
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
            parsed = parse_plan_csv(handle.read(), name)
        out.rows += parsed.rows
        out.report.merge(parsed.report)
    return out


# ------------------------------------------------------------------------------- write
def write_plan_rows(store: Any, rows: Iterable[PlanCsvRow]) -> int:
    """Write rows, in order, into an empty plan (an open, writable ``PlanStore``).

    One transaction: on any error nothing is written. ``sort_order`` counts per section.
    Returns the number of rows written.
    """
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


def import_plan_csv_set(folder: str | Path, store: Any, files: Iterable[str] = PLAN_CSV_FILES) -> ImportReport:
    """Read the plan CSV set from ``folder`` and write it into the empty plan ``store``."""
    parsed = read_plan_csv_set(folder, files)
    parsed.report.rows = write_plan_rows(store, parsed.rows)
    return parsed.report
