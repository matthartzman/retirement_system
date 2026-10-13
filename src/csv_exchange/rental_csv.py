"""Rental properties as CSV (WP12.9): the three typed tables as three files of one dataset.

``rental_properties.csv``       one row per property (``name`` + the property columns)
``rental_improvements.csv``     ``property`` (the property's name), ``year``, ``month``, ``amount``, ``description``
``rental_year_overrides.csv``   ``property``, ``year``, ``gross_rent``, ``operating_expenses``, ``notes``

The dataset ``rental_properties`` (``core.DATASETS``) holds the rows of all three files tagged
by a ``_file`` column, so the core's parse / validate / preview / diff / commit run on it like
on any other dataset. An import REPLACES the whole set (a file left out clears its table);
unknown columns are dropped with a warning; every row is checked with
``parse_rental_properties`` (the same boundary the engine uses) and a bad row is an error
naming its row and property. The import writes whether or not the ``rental_property_income``
feature is on: rows are kept while it is off. Cells are written the way the parser reads
them (numbers plain, ``yes`` / ``no`` flags), so an export, import and export is byte-stable.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Mapping, Sequence

from ..parsing.rental_properties import RentalPropertyInputError, parse_rental_properties
from ..stores.rental_repo import (
    BOOL_COLUMNS, IMPROVEMENT_KEYS, OVERRIDE_KEYS, PROPERTY_COLUMNS)

DATASET = "rental_properties"
PROPERTIES_FILE = "rental_properties.csv"
IMPROVEMENTS_FILE = "rental_improvements.csv"
OVERRIDES_FILE = "rental_year_overrides.csv"
FILES = (PROPERTIES_FILE, IMPROVEMENTS_FILE, OVERRIDES_FILE)
PART_PROPERTY, PART_IMPROVEMENT, PART_OVERRIDE = "property", "improvement", "override"
_PART_OF_FILE = dict(zip(FILES, (PART_PROPERTY, PART_IMPROVEMENT, PART_OVERRIDE)))
_FILE_OF_PART = {v: k for k, v in _PART_OF_FILE.items()}

# File column order (the template and the export write exactly these).
FILE_COLUMNS: dict[str, tuple[str, ...]] = {
    PROPERTIES_FILE: ("name", *PROPERTY_COLUMNS),
    IMPROVEMENTS_FILE: ("property", *IMPROVEMENT_KEYS),
    OVERRIDES_FILE: ("property", *OVERRIDE_KEYS),
}
REQUIRED = {PROPERTIES_FILE: ("name",), IMPROVEMENTS_FILE: ("property",), OVERRIDES_FILE: ("property", "year")}
# Row shape inside ParsedDataset: ``_file`` part tag, ``property`` = the owning property's name.
COLUMNS = ("_file", "property", *dict.fromkeys(
    c for cols in FILE_COLUMNS.values() for c in cols if c not in ("name", "property")))
KEY = ("_file", "property", "year")


def _cell(v: Any, column: str) -> str:
    if v is None:
        return ""
    if column in BOOL_COLUMNS:
        return "yes" if v else "no"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return str(v)


def rows_from_properties(props: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Repository rows -> dataset rows (properties, then improvements, then overrides)."""
    out: list[dict[str, str]] = []
    for part, file in _FILE_OF_PART.items():
        for p in props:
            if part == PART_PROPERTY:
                recs = [p]
            else:
                recs = p.get("improvements" if part == PART_IMPROVEMENT else "overrides", [])
            for rec in recs:
                row = {c: "" for c in COLUMNS}
                row["_file"], row["property"] = part, str(p["name"])
                for c in FILE_COLUMNS[file]:
                    if c not in ("name", "property"):
                        row[c] = _cell(rec.get(c), c)
                out.append(row)
    return out


def properties_from_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    """Dataset rows -> ``parse_rental_properties`` input rows. A child row whose property is
    not in the properties file is left out here and reported by :func:`validate_rows`."""
    props: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rows:
        if r.get("_file") != PART_PROPERTY:
            continue
        name = str(r.get("property", "")).strip()
        p = {c: r.get(c, "") for c in PROPERTY_COLUMNS if str(r.get(c, "")).strip()}
        p.update(name=name, improvements=[], overrides=[])
        key = name.casefold()
        if key not in props:
            order.append(key)
        props[key] = p
    for r in rows:
        part = r.get("_file")
        if part == PART_PROPERTY:
            continue
        p = props.get(str(r.get("property", "")).strip().casefold())
        if p is None:
            continue
        cols = IMPROVEMENT_KEYS if part == PART_IMPROVEMENT else OVERRIDE_KEYS
        p["improvements" if part == PART_IMPROVEMENT else "overrides"].append(
            {c: r.get(c, "") for c in cols if str(r.get(c, "")).strip()})
    return [props[k] for k in order]


def current_rows(store: Any) -> list[dict[str, str]]:
    return rows_from_properties(store.rental.properties())


def write_rows(store: Any, rows: Sequence[Mapping[str, str]]) -> int:
    """Replace the plan's rental set with ``rows``; returns the number of properties."""
    return store.rental.replace_all(properties_from_rows(rows))


# ------------------------------------------------------------------------------ parse
def parse_files(texts: Mapping[str, str]) -> tuple[list[str], list[dict[str, str]], list[tuple[str, str, str]]]:
    """``{file: text}`` -> ``(header, rows, problems)``; problems are ``(level, message, column)``.
    Unknown columns are dropped (a warning each); a missing required column is an error."""
    from .flat_csv import dataset_rows_from_csv_text  # noqa: PLC0415 - sibling, avoids an import cycle at load
    header: list[str] = []
    rows: list[dict[str, str]] = []
    problems: list[tuple[str, str, str]] = []
    for file_name, body in texts.items():
        file = next((f for f in FILES if f.lower() == file_name.lower()), file_name)
        cols = FILE_COLUMNS.get(file)
        file_header, file_rows = dataset_rows_from_csv_text(body)
        if cols is None or not file_header:
            problems.append(("error", f"{file_name}: empty or missing a header row", ""))
            continue
        missing = [c for c in REQUIRED[file] if c not in file_header]
        if missing:
            problems.append(("error", f"{file_name}: missing required column(s): {', '.join(missing)}", ""))
        unknown = [c for c in file_header if c not in cols]
        if unknown:
            problems.append(("warning", f"{file_name}: ignored unknown column(s): {', '.join(unknown)}", ""))
        header += [c for c in file_header if c in cols and c not in header]
        for raw in file_rows:
            row = {c: "" for c in COLUMNS}
            row["_file"] = _PART_OF_FILE[file]
            row["property"] = raw.get("name" if file == PROPERTIES_FILE else "property", "").strip()
            for c in cols:
                if c not in ("name", "property") and c in raw:
                    row[c] = raw[c].strip()
            rows.append(row)
    return header, rows, problems


# --------------------------------------------------------------------------- validate
def validate_rows(rows: Sequence[Mapping[str, str]]) -> list[tuple[str, str, int | None, str]]:
    """Row-level issues ``(level, message, 1-based row, column)``: orphaned or unnamed rows,
    then each property through ``parse_rental_properties`` (its message names the field),
    then the whole set (duplicate names, one converted home, the property limit)."""
    out: list[tuple[str, str, int | None, str]] = []
    names = {str(r["property"]).strip().casefold() for r in rows if r.get("_file") == PART_PROPERTY and str(r["property"]).strip()}
    for n, r in enumerate(rows, 1):
        name = str(r.get("property", "")).strip()
        if not name:
            out.append(("error", "property name is blank", n, "name" if r["_file"] == PART_PROPERTY else "property"))
        elif r["_file"] != PART_PROPERTY and name.casefold() not in names:
            out.append(("error", f"{name!r} is not in {PROPERTIES_FILE}", n, "property"))
    props = properties_from_rows(rows)
    prop_row = {str(r["property"]).strip().casefold(): n for n, r in enumerate(rows, 1) if r["_file"] == PART_PROPERTY}
    bad = False
    for p in props:
        try:
            parse_rental_properties({}, [p])
        except RentalPropertyInputError as exc:
            bad = True
            out.append(("error", str(exc), prop_row.get(p["name"].casefold()), ""))
    if not bad:
        try:
            parse_rental_properties({}, props)
        except RentalPropertyInputError as exc:
            out.append(("error", str(exc), None, ""))
    return out


# ------------------------------------------------------------------- export / template
def _csv_text(file: str, rows: Sequence[Mapping[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    cols = FILE_COLUMNS[file]
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get("property" if c == "name" else c, "") for c in cols])
    return buf.getvalue()


def export_files(rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """Dataset rows -> ``{file: CSV text}`` (all three files, header only when empty)."""
    return {f: _csv_text(f, [r for r in rows if r["_file"] == _PART_OF_FILE[f]]) for f in FILES}


def export_dataset(store: Any) -> dict[str, str]:
    return export_files(current_rows(store))


_EXAMPLE = {
    "name": "Maple Street duplex", "kind": "standalone", "purchase_price": "320000", "closing_costs": "6400",
    "purchase_year": "2021", "purchase_month": "3", "land_share": "0.2", "monthly_rent": "2400",
    "vacancy_rate": "0.05", "maintenance_pct": "0.01", "management_pct": "0.08", "property_tax": "4800",
    "insurance": "1500", "appreciation": "0.03", "rent_growth": "0.03", "expense_growth": "0.03",
    "property_tax_growth": "0.02", "active_participation": "yes", "notes": "Example row - delete or edit",
}


def template_files() -> dict[str, str]:
    """A blank import template: each file's headers, and one example property with an
    improvement and a year override. It parses clean, so a user can import it as is."""
    ex = {**{c: "" for c in COLUMNS}, "_file": PART_PROPERTY, "property": _EXAMPLE["name"], **_EXAMPLE}
    imp = {**{c: "" for c in COLUMNS}, "_file": PART_IMPROVEMENT, "property": _EXAMPLE["name"],
           "year": "2023", "month": "5", "amount": "12000", "description": "New roof"}
    ovr = {**{c: "" for c in COLUMNS}, "_file": PART_OVERRIDE, "property": _EXAMPLE["name"],
           "year": "2025", "gross_rent": "30000", "operating_expenses": "9000", "notes": "Actual from Schedule E"}
    return export_files([ex, imp, ovr])
