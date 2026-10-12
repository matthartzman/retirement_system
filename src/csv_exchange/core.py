"""The schema-driven import/export core of ``csv_exchange`` (design F section 6, P7.1 / WP9.1).

The file-shape -> table mapping is declared ONCE, in :data:`DATASETS` (one
:class:`DatasetSpec` per dataset: the files it comes from, the table it lands in, its
columns, its identity key, the columns it requires and how an import writes it). Every
import goes the same way:

    parsed = parse(text, "holdings")          # text (or {file: text}) -> rows + issues
    report = preview(store, parsed)           # validation + diff against the store; writes nothing
    commit(store, parsed)                     # one transaction: all datasets or none

and every export is ``export_dataset(store, name)`` (CSV text). Nothing here touches the file
system or a server: callers hand in text and get text back.

Rules that keep numbers from moving: cells are kept exactly as the file had them (flat
datasets: unstripped, as ``flat_csv`` stores them; the plan CSV set: stripped, as
``plan_csv`` stores it), no value is reformatted, and an export writes the stored text.

Stores. ``plan_rows`` and the flat datasets live in the plan file (``PlanStore``); the
capital-market assumptions, correlations and security master live in the read-only
``reference.db`` (``RefData``), so their specs are not writable yet: they parse, validate,
preview, diff and export, and ``commit`` refuses them until a writable override store exists
(P7.3/P7.4). Monarch outbox files map onto ``ytd_transactions`` and merge by ``Monarch Id``.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from .flat_csv import FLAT_DATASET_FILES, dataset_csv_text, dataset_rows_from_csv_text
from .plan_csv import PLAN_CSV_FILES, collapse_duplicate_keys, parse_plan_csv

PLAN_ROWS = "plan_rows"
TARGET_PLAN_ROWS = "plan_rows"      # store.all_rows / insert_row
TARGET_PLAN_DATASET = "plan_dataset"  # store.dataset(table)
TARGET_REFERENCE = "reference"       # RefData.table(table), read-only
MODE_REPLACE = "replace"             # the incoming rows become the dataset
MODE_UPSERT = "upsert"               # incoming rows replace same-key rows, others are appended

SAMPLE_LIMIT = 5


# ------------------------------------------------------------------------------ specs
@dataclass(frozen=True)
class DatasetSpec:
    """How one dataset's file shape maps to its table (declared once, in :data:`DATASETS`)."""
    name: str
    files: tuple[str, ...]               # file names it is read from / exported as (first = export)
    target: str                          # TARGET_PLAN_ROWS | TARGET_PLAN_DATASET | TARGET_REFERENCE
    table: str                           # store.dataset(name) / reference table
    columns: tuple[str, ...]
    key: tuple[str, ...] = ()            # identity columns for the diff ((): the whole row)
    required: tuple[str, ...] = ()       # header columns an incoming file must carry
    numeric: tuple[str, ...] = ()        # columns whose non-blank cells must parse as numbers
    mode: str = MODE_REPLACE
    column_map: Mapping[str, str] = field(default_factory=dict)  # file column -> table column ('' drops it)
    group: str = ""                      # export/import group (plan_set, holdings, ytd, spending ...)

    @property
    def writable(self) -> bool:
        return self.target != TARGET_REFERENCE

    @property
    def identity(self) -> tuple[str, ...]:
        return self.key or self.columns


def _flat_columns(name: str) -> tuple[str, ...]:
    from ..stores.datasets import _DATASETS  # noqa: PLC0415 - the table catalog is the column source
    return _DATASETS["holdings_lots" if name == "holdings" else name]


# Flat plan dataset -> (identity key, required header columns, numeric columns, group).
_FLAT_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str]] = {
    "holdings": ((), ("account", "symbol", "shares"), ("shares", "purchase_price"), "holdings"),
    "liabilities": (("liability_id",), ("liability_id",),
                    ("balance", "interest_rate", "monthly_payment"), "plan_set"),
    "hsa_schedule": (("year",), ("year",), ("optimizer_amount", "override_amount"), "plan_set"),
    "target_allocation": (("asset_class",), ("asset_class", "target_pct"), ("target_pct",), "plan_set"),
    "spending_taxonomy": (("category_id",), ("category_id",), (), "spending"),
    "spending_aliases": (("match_value", "match_field"), ("match_value", "category_id"), (), "spending"),
    "spending_budget": (("kind", "key"), ("kind", "key"), ("annual_budget",), "spending"),
    "spending_budget_lines": (("section", "line_id"), ("line_id",), ("amount_per_year",), "spending"),
    "spending_tier_overrides": (("category_id",), ("category_id", "tier"), (), "spending"),
    "spending_rules": (("keyword", "match_field"), ("keyword", "category_id"), (), "spending"),
    "spending_category_map": (("category",), ("category",), (), "spending"),
    "spending_group_budget": (("group",), ("group",), ("budget_pct", "budget_override"), "spending"),
    "ytd_transactions": ((), ("Date", "Amount"), ("Amount",), "ytd"),
    "ytd_account_setup": (("Account",), ("Account",),
                          ("Prior Year End Balance", "Current Value", "Current Balance"), "ytd"),
    "ytd_import_history": ((), (), (), "ytd"),
}

# Monarch Extractor outbox columns -> ytd_transactions columns (monarch_import's fallback map).
MONARCH_COLUMN_MAP: dict[str, str] = {
    "id": "Monarch Id", "date": "Date", "merchant": "Merchant", "category": "Category",
    "account": "Account", "original_statement": "Original Statement", "notes": "Notes",
    "amount": "Amount", "tags": "Tags", "owner": "Owner", "run_id": "",
}

_REFERENCE_SPECS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    # name, file, columns, key, required, numeric
    ("cma", "custom_cma.csv",
     ("horizon_years", "preset", "asset_class", "expected_return", "volatility", "stock_index_correlation",
      "notes", "distribution_yield", "qualified_dividend_fraction", "tax_exempt_yield"),
     ("horizon_years", "preset", "asset_class"), ("asset_class", "expected_return", "volatility"),
     ("expected_return", "volatility", "stock_index_correlation", "distribution_yield",
      "qualified_dividend_fraction", "tax_exempt_yield")),
    ("correlation", "custom_correlations.csv",
     ("horizon_years", "preset", "asset_class_a", "asset_class_b", "correlation", "notes"),
     ("horizon_years", "preset", "asset_class_a", "asset_class_b"),
     ("asset_class_a", "asset_class_b", "correlation"), ("correlation",)),
    ("security_master", "security_master.csv",
     ("symbol", "asset_class", "sleeve", "region", "style", "notes"),
     ("symbol",), ("symbol", "asset_class"), ()),
)


def _build_registry() -> dict[str, DatasetSpec]:
    out: dict[str, DatasetSpec] = {
        PLAN_ROWS: DatasetSpec(
            name=PLAN_ROWS, files=PLAN_CSV_FILES, target=TARGET_PLAN_ROWS, table="plan_rows",
            columns=("section", "subsection", "label", "value", "units", "notes"),
            key=("section", "subsection", "label"), required=("section", "label"), group="plan_set"),
    }
    for name, file_name in FLAT_DATASET_FILES.items():
        key, required, numeric, group = _FLAT_RULES[name]
        out[name] = DatasetSpec(name=name, files=(file_name,), target=TARGET_PLAN_DATASET, table=name,
                                columns=_flat_columns(name), key=key, required=required,
                                numeric=numeric, group=group)
    out["monarch_transactions"] = DatasetSpec(
        name="monarch_transactions", files=("new_transactions.csv", "changed_transactions.csv"),
        target=TARGET_PLAN_DATASET, table="ytd_transactions", columns=_flat_columns("ytd_transactions"),
        key=("Monarch Id",), required=("id", "date", "amount"), numeric=("Amount",),
        mode=MODE_UPSERT, column_map=MONARCH_COLUMN_MAP, group="monarch")
    for name, file_name, cols, key, required, numeric in _REFERENCE_SPECS:
        out[name] = DatasetSpec(name=name, files=(file_name,), target=TARGET_REFERENCE, table=name,
                                columns=cols, key=key, required=required, numeric=numeric, group="reference")
    return out


DATASETS: dict[str, DatasetSpec] = _build_registry()


def dataset_spec(name: str) -> DatasetSpec:
    try:
        return DATASETS[name]
    except KeyError:
        raise KeyError(f"unknown csv_exchange dataset {name!r}") from None


def dataset_for_file(file_name: str) -> DatasetSpec | None:
    """The dataset a file name belongs to (case-insensitive), or ``None``."""
    low = file_name.strip().lower()
    for spec in DATASETS.values():
        if any(f.lower() == low for f in spec.files):
            return spec
    return None


# ------------------------------------------------------------------------------ parse
@dataclass(frozen=True)
class Issue:
    level: str          # "error" (blocks commit) | "warning"
    message: str
    row: int | None = None   # 1-based data-row index in the incoming rows
    column: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level, "message": self.message, "row": self.row, "column": self.column}


@dataclass
class ParsedDataset:
    """Incoming rows of one dataset, keyed by the table's column names."""
    name: str
    header: list[str]
    rows: list[dict[str, str]]
    parse_issues: list[Issue] = field(default_factory=list)   # found by parse (header, shape)
    issues: list[Issue] = field(default_factory=list)         # parse issues + validate's checks

    def __post_init__(self) -> None:
        if not self.issues:
            self.issues = list(self.parse_issues)

    @property
    def spec(self) -> DatasetSpec:
        return dataset_spec(self.name)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


def parse(text: str | Mapping[str, str], name: str) -> ParsedDataset:
    """CSV text (or ``{file name: text}`` for a multi-file dataset) -> the dataset's rows.

    Header problems (a missing required column, a file that is not the right shape) are
    recorded as errors, never raised; :func:`validate` adds the per-row checks."""
    spec = dataset_spec(name)
    texts = dict(text) if isinstance(text, Mapping) else {spec.files[0]: text}
    if spec.target == TARGET_PLAN_ROWS:
        return _parse_plan_rows(spec, texts)
    header: list[str] = []
    rows: list[dict[str, str]] = []
    issues: list[Issue] = []
    for file_name, body in texts.items():
        file_header, file_rows = dataset_rows_from_csv_text(body)
        if not file_header:
            issues.append(Issue("error", f"{file_name}: empty or missing a header row"))
            continue
        missing = [c for c in spec.required if c not in file_header]
        if missing:
            issues.append(Issue("error", f"{file_name}: missing required column(s): {', '.join(missing)}"))
        mapped = [_map_column(spec, c) for c in file_header]
        for c in mapped:
            if c and c not in header:
                header.append(c)
        for raw in file_rows:
            row: dict[str, str] = {}
            for k, v in raw.items():
                target = _map_column(spec, k)
                if target:
                    row[target] = v
            for c in spec.columns:
                row.setdefault(c, "")
            rows.append(row)
    return ParsedDataset(name, header, rows, issues)


def _map_column(spec: DatasetSpec, column: str) -> str:
    if not spec.column_map:
        return column
    return spec.column_map.get(column, spec.column_map.get(column.strip().lower(), column))


def _parse_plan_rows(spec: DatasetSpec, texts: Mapping[str, str]) -> ParsedDataset:
    from .plan_csv import PlanCsvError  # noqa: PLC0415

    parsed_rows = []
    issues: list[Issue] = []
    for file_name, body in texts.items():
        try:
            parsed = parse_plan_csv(body, file_name)
        except PlanCsvError as exc:
            issues.append(Issue("error", str(exc)))
            continue
        parsed_rows += parsed.rows
        for s in parsed.report.skipped:
            issues.append(Issue("warning", f"{s.source_file} line {s.line}: skipped ({s.reason})"))
    collapsed, dups = collapse_duplicate_keys(parsed_rows)
    if dups:
        issues.append(Issue("warning", f"{dups} duplicate key row(s) collapsed (last value wins)"))
    rows = [{"section": r.section, **r.fields()} for r in collapsed]
    return ParsedDataset(spec.name, list(spec.columns), rows, issues)


# --------------------------------------------------------------------------- validate
SchemaFields = Mapping[tuple[str, str, str], Mapping[str, str]]


def _is_number(text: str) -> bool:
    t = text.strip().replace("$", "").replace(",", "").replace("%", "")
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1]
    try:
        float(t)
    except ValueError:
        return False
    return True


def validate(parsed: ParsedDataset, *, schema: SchemaFields | None = None,
             value_check: Callable[[str, Mapping[str, str]], list[str]] | None = None) -> list[Issue]:
    """All issues of ``parsed``: its parse issues plus per-row checks (returned, also kept on
    ``parsed.issues``). Plan rows are checked against ``schema_fields`` (``schema`` defaults to
    the shipped catalog): a value failing its field's type/range is an error, a key the
    catalog does not know is counted in one summary warning. Flat rows: a blank required
    cell and a non-numeric cell in a numeric column are errors. Calling it again recomputes."""
    spec = parsed.spec
    issues = list(parsed.parse_issues)
    if spec.target == TARGET_PLAN_ROWS:
        if schema is None:
            from ..schema_registry import load_schema  # noqa: PLC0415
            schema = load_schema()
        if value_check is None:
            from ..schema_registry import validate_value as value_check  # noqa: PLC0415
        unknown: list[str] = []
        for n, row in enumerate(parsed.rows, 1):
            key = (row["section"], row["subsection"], row["label"])
            field_spec = schema.get(key)
            if field_spec is None:
                unknown.append(" / ".join(key))
                continue
            for msg in value_check(row.get("value", ""), field_spec):
                issues.append(Issue("error", f"{' / '.join(key)}: {msg}", n, "value"))
        if unknown:  # one summary warning: many legitimate rows (lists, notes) have no catalog entry
            shown = "; ".join(unknown[:SAMPLE_LIMIT]) + (" ..." if len(unknown) > SAMPLE_LIMIT else "")
            issues.append(Issue("warning", f"{len(unknown)} row(s) not in the field catalog: {shown}"))
    else:
        for n, row in enumerate(parsed.rows, 1):
            for c in spec.required:
                if c in spec.columns and not str(row.get(c, "")).strip():
                    issues.append(Issue("error", f"{c} is blank", n, c))
            for c in spec.numeric:
                v = str(row.get(c, "") or "")
                if v.strip() and not _is_number(v):
                    issues.append(Issue("error", f"{c} {v!r} is not a number", n, c))
    parsed.issues = issues
    return issues


# ------------------------------------------------------------------------- store reads
def current_rows(store: Any, name: str) -> list[dict[str, str]]:
    """The dataset's rows as the store holds them, keyed by the spec's columns (text)."""
    spec = dataset_spec(name)
    if spec.target == TARGET_PLAN_ROWS:
        out = []
        for section in store.section_order():
            for r in store.rows(section):
                out.append({c: str(r.get(c) or "") for c in spec.columns})
        return out
    if spec.target == TARGET_PLAN_DATASET:
        return store.dataset(spec.table).rows()
    return [{c: _ref_text(r.get(c)) for c in spec.columns} for r in store.table(spec.table)]


def _ref_text(v: Any) -> str:
    return "" if v is None else str(v)


# ----------------------------------------------------------------------- diff/preview
@dataclass
class Diff:
    added: list[dict[str, str]] = field(default_factory=list)
    removed: list[dict[str, str]] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)   # {key, before, after, fields}
    unchanged: int = 0

    def summary(self, sample: int = SAMPLE_LIMIT) -> dict[str, Any]:
        return {
            "added": len(self.added), "changed": len(self.changed),
            "removed": len(self.removed), "unchanged": self.unchanged,
            "samples": {"added": self.added[:sample], "changed": self.changed[:sample],
                        "removed": self.removed[:sample]},
        }


def _norm(row: Mapping[str, Any], columns: Iterable[str]) -> dict[str, str]:
    return {c: "" if row.get(c) is None else str(row.get(c)) for c in columns}


def diff_rows(spec: DatasetSpec, before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]) -> Diff:
    """Rows of ``after`` against ``before`` by the spec's identity key. Rows sharing a key are
    paired in order; a keyless spec compares whole rows (a row is added or removed, never
    changed)."""
    extra = sorted({k for r in [*before, *after] for k in r} - set(spec.columns))
    cols = [*spec.columns, *extra]
    ident = spec.identity
    old: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for r in before:
        n = _norm(r, cols)
        old.setdefault(tuple(n.get(c, "") for c in ident), []).append(n)
    out = Diff()
    for r in after:
        n = _norm(r, cols)
        k = tuple(n.get(c, "") for c in ident)
        bucket = old.get(k)
        if not bucket:
            out.added.append(n)
            continue
        prev = bucket.pop(0)
        if prev == n:
            out.unchanged += 1
        else:
            fields = [c for c in cols if prev.get(c, "") != n.get(c, "")]
            out.changed.append({"key": dict(zip(ident, k)), "before": prev, "after": n, "fields": fields})
    for bucket in old.values():
        out.removed += bucket
    return out


def _result_rows(spec: DatasetSpec, before: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    """What the dataset holds after the import (``replace``: the incoming rows; ``upsert``:
    the current rows with same-key rows replaced in place and new rows appended)."""
    if spec.mode == MODE_REPLACE:
        return list(incoming)
    ident = spec.identity
    merged = [dict(r) for r in before]
    where = {tuple(r.get(c, "") for c in ident): i for i, r in enumerate(merged)}
    for r in incoming:
        k = tuple(r.get(c, "") for c in ident)
        if k in where and any(k):
            merged[where[k]] = dict(r)
        else:
            where[k] = len(merged)
            merged.append(dict(r))
    return merged


def _as_list(incoming: ParsedDataset | Iterable[ParsedDataset]) -> list[ParsedDataset]:
    return [incoming] if isinstance(incoming, ParsedDataset) else list(incoming)


def preview(store: Any, incoming: ParsedDataset, *, schema: SchemaFields | None = None,
            sample: int = SAMPLE_LIMIT) -> dict[str, Any]:
    """What committing ``incoming`` would do, without writing: validation issues and the diff
    (added / changed / removed / unchanged counts plus sample rows)."""
    spec = incoming.spec
    issues = validate(incoming, schema=schema)
    before = current_rows(store, spec.name)
    after = _result_rows(spec, before, incoming.rows)
    errors = [i.as_dict() for i in issues if i.level == "error"]
    return {
        "schema": "csv_exchange_preview_v1",
        "dataset": spec.name,
        "table": spec.table,
        "mode": spec.mode,
        "writable": spec.writable,
        "rows_incoming": len(incoming.rows),
        "rows_current": len(before),
        "rows_after": len(after),
        "errors": errors,
        "warnings": [i.as_dict() for i in issues if i.level == "warning"],
        "diff": diff_rows(spec, before, after).summary(sample),
        "will_write": spec.writable and not errors,
    }


# ----------------------------------------------------------------------------- commit
class ImportRejected(ValueError):
    """The import was refused before anything was written (validation errors, read-only
    dataset). ``issues`` lists why."""

    def __init__(self, message: str, issues: Sequence[Issue] = ()) -> None:
        super().__init__(message)
        self.issues = list(issues)


def commit(store: Any, incoming: ParsedDataset | Iterable[ParsedDataset], *,
           schema: SchemaFields | None = None, allow_errors: bool = False) -> dict[str, int]:
    """Write one or more parsed datasets in ONE store transaction: either every dataset is
    written or none is. Validates first and refuses (``ImportRejected``, nothing written) on
    an error unless ``allow_errors``. Returns ``{dataset: rows the dataset now holds}``."""
    parts = _as_list(incoming)
    for p in parts:
        if not p.spec.writable:
            raise ImportRejected(f"{p.name}: dataset is read-only (reference data)")
        errors = [i for i in validate(p, schema=schema) if i.level == "error"]
        if errors and not allow_errors:
            raise ImportRejected(f"{p.name}: {len(errors)} validation error(s); nothing written", errors)
    out: dict[str, int] = {}
    with store.transaction():
        for p in parts:
            spec = p.spec
            if spec.target == TARGET_PLAN_ROWS:
                out[spec.name] = _write_plan_rows(store, _result_rows(spec, current_rows(store, spec.name), p.rows))
            else:
                repo = store.dataset(spec.table)
                rows = _result_rows(spec, repo.rows() if spec.mode != MODE_REPLACE else [], p.rows)
                out[spec.name] = repo.replace_all(rows)
    return out


def _write_plan_rows(store: Any, rows: Sequence[Mapping[str, str]]) -> int:
    store.clear_rows()
    next_order: dict[str, int] = {}
    for r in rows:
        order = next_order.get(r["section"], 0)
        next_order[r["section"]] = order + 1
        store.insert_row(r["section"], subsection=r.get("subsection", ""), label=r.get("label", ""),
                         value=r.get("value", ""), units=r.get("units", ""), notes=r.get("notes", ""),
                         sort_order=order)
    return len(rows)


# ----------------------------------------------------------------------------- export
def export_dataset(store: Any, name: str) -> str:
    """The dataset as CSV text (header line, then one line per row, cells as stored)."""
    spec = dataset_spec(name)
    if spec.target == TARGET_PLAN_DATASET and spec.mode == MODE_REPLACE:
        return dataset_csv_text(store.dataset(spec.table))
    if spec.mode == MODE_UPSERT:
        raise KeyError(f"{name} is an import-only shape; export {spec.table!r} instead")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(spec.columns)
    for r in current_rows(store, name):
        w.writerow([r.get(c, "") for c in spec.columns])
    return buf.getvalue()
