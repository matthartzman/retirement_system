"""Plan-side override tables: custom capital-market assumptions, custom correlations and
custom real-loss curves (WP3.4/WP3.5 override rows, stored in ``plan_rows`` since WP4.5).

The shipped reference data (``reference.db``) is read-only. A plan may carry expert override
tables over it. Each is a small table of rows with named columns; in ``plan_rows`` a table is a
section and a row is a numbered subsection, one plan row per cell::

    Custom Capital Market / row_1 / horizon_years       30
    Custom Capital Market / row_1 / preset               BASELINE
    Custom Capital Market / row_1 / asset_class          US Equity
    Custom Capital Market / row_1 / expected_return      7.5%
    ...

:func:`override_rows` reads one table back as the list of ``{column: text}`` dicts the engine's
loaders take (the same shape ``csv.DictReader`` gave the old custom files, and the shipped
rows). The engine config gets them as ``capital_market_config['custom_capital_market_rows']``,
``capital_market_config['custom_correlation_rows']`` and ``c['real_loss_curve_rows']`` (see
``parsing.allocation_optimizer_inputs`` and ``data_io.parse_client``); a plan with no rows in a
table has no such key, which the engine reads as "use the shipped table". The tables apply only
when the capital-market config selects custom assumptions (``use_custom_*_file`` / mode
``CUSTOM_FILE``), exactly as the old files did.

:func:`validate_rows` is the typed check of a posted table (numbers parse, asset classes and
presets are known); :func:`replace_rows` writes a validated table into an open plan, replacing
the previous rows of that table.

Accepted cell forms (the engine reads them with ``optimization._parse_number``, which divides a
value ending in ``%`` by 100 and takes anything else as it stands):

* ``horizon_years``, ``holding_years``: whole numbers (``30``), never a percent.
* ``expected_return``, ``volatility``: a percent (``7.5%``) or a fraction (``0.075``). A bare number
  outside -1..1 is refused (``7.5`` would be read as 750%; write ``7.5%``). Volatility is not negative.
* ``stock_index_correlation``, ``correlation``: a fraction or percent whose value is between -1 and 1.
* ``real_loss_prob``: a fraction or percent between 0 and 1 (0%-100%).

A stored cell is the typed text with spaces, thousands commas and a leading ``+`` removed; the digits
and a trailing ``%`` are kept as typed, so the engine reads exactly what the user wrote. Rows whose
cells are all empty are dropped (a grid's blank trailing rows); a table posted with only empty rows
is refused (post ``[]`` to clear it).
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

CMA = "capital_market"
CORRELATIONS = "correlations"
REAL_LOSS = "real_loss"

SECTIONS = {
    CMA: "Custom Capital Market",
    CORRELATIONS: "Custom Correlations",
    REAL_LOSS: "Custom Real Loss Curves",
}
# Column order of a stored row; the first ones are the key columns, the rest are values.
COLUMNS = {
    CMA: ("horizon_years", "preset", "asset_class", "expected_return", "volatility", "stock_index_correlation"),
    CORRELATIONS: ("horizon_years", "preset", "asset_class_a", "asset_class_b", "correlation"),
    REAL_LOSS: ("curve_name", "holding_years", "real_loss_prob"),
}
# Columns that may be left empty (an empty horizon/preset applies to every horizon/preset).
OPTIONAL = {
    CMA: ("horizon_years", "preset", "expected_return", "volatility", "stock_index_correlation"),
    CORRELATIONS: ("horizon_years", "preset"),
    REAL_LOSS: (),
}
NUMBER_COLUMNS = {
    CMA: ("horizon_years", "expected_return", "volatility", "stock_index_correlation"),
    CORRELATIONS: ("horizon_years", "correlation"),
    REAL_LOSS: ("holding_years", "real_loss_prob"),
}
# Number columns that may carry a trailing ``%`` (the rest are whole numbers).
PERCENT_COLUMNS = {
    CMA: ("expected_return", "volatility", "stock_index_correlation"),
    CORRELATIONS: ("correlation",),
    REAL_LOSS: ("real_loss_prob",),
}
INTEGER_COLUMNS = {
    CMA: ("horizon_years",),
    CORRELATIONS: ("horizon_years",),
    REAL_LOSS: ("holding_years",),
}
# Inclusive value range of a percent column (as a fraction); ``None`` = unbounded.
VALUE_RANGE = {
    "expected_return": (-1.0, None),
    "volatility": (0.0, None),
    "stock_index_correlation": (-1.0, 1.0),
    "correlation": (-1.0, 1.0),
    "real_loss_prob": (0.0, 1.0),
}
# Columns whose bare (no ``%``) value must already be a fraction.
FRACTION_IF_BARE = ("expected_return", "volatility")
ASSET_CLASS_COLUMNS = {CMA: ("asset_class",), CORRELATIONS: ("asset_class_a", "asset_class_b"), REAL_LOSS: ()}
UNITS = "text"
_ROW_SUBSECTION = re.compile(r"^row_(\d+)$")
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)%?$")
_INTEGER = re.compile(r"^\d+$")


class OverrideRowsError(ValueError):
    """A posted table is not acceptable; ``errors`` lists every problem (nothing was written)."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def _normalise_number(text: str) -> str:
    """The typed text without spaces, thousands commas and a leading ``+`` (digits and ``%`` as typed)."""
    out = str(text).replace(",", "").replace(" ", "").replace("\u00a0", "")
    return out[1:] if out.startswith("+") else out


def _number_ok(text: str) -> bool:
    return bool(_NUMBER.match(_normalise_number(text)))


def _fraction(text: str) -> float:
    """The value of a number cell as the engine reads it (a trailing ``%`` divides by 100)."""
    norm = _normalise_number(text)
    return float(norm.rstrip("%")) / (100.0 if norm.endswith("%") else 1.0)


def _is_blank_row(row: Mapping[str, Any], columns: Iterable[str]) -> bool:
    return not any(str(row.get(col) if row.get(col) is not None else "").strip() for col in columns)


def override_rows(data: Mapping[str, Any], kind: str) -> list[dict[str, str]]:
    """The stored table ``kind`` from a sectioned plan view (``{section: {subsection: {label:
    value}}}``): one dict per ``row_N`` subsection in number order, holding only the known
    columns that have a value. A row with no value at all is skipped."""
    section = (data or {}).get(SECTIONS[kind]) or {}
    columns = COLUMNS[kind]
    numbered = []
    for subsection, values in section.items():
        m = _ROW_SUBSECTION.match(str(subsection))
        if m and isinstance(values, Mapping):
            numbered.append((int(m.group(1)), values))
    out: list[dict[str, str]] = []
    for _n, values in sorted(numbered, key=lambda t: t[0]):
        row = {col: str(values[col]).strip() for col in columns if str(values.get(col, "")).strip()}
        if row:
            out.append(row)
    return out


def validate_rows(kind: str, rows: Any) -> list[dict[str, str]]:
    """Return the clean rows (every cell a stripped string, only known columns) or raise
    :class:`OverrideRowsError` listing every problem."""
    if not isinstance(rows, list):
        raise OverrideRowsError(["rows must be a list of objects"])
    from .allocation_policy import canonical_asset_class  # noqa: PLC0415 - keeps the parser import light
    from .optimization import CAPITAL_MARKET_PRESETS, _BASE_ASSET_CLASSES  # noqa: PLC0415

    columns, optional = COLUMNS[kind], OPTIONAL[kind]
    errors: list[str] = []
    clean: list[dict[str, str]] = []
    skipped_blank = 0
    for i, raw in enumerate(rows, 1):
        if not isinstance(raw, Mapping):
            errors.append(f"row {i}: must be an object")
            continue
        unknown = sorted(set(map(str, raw)) - set(columns))
        if unknown:
            errors.append(f"row {i}: unknown column(s) {', '.join(unknown)}")
        if _is_blank_row(raw, columns):  # a grid's blank trailing row
            skipped_blank += 1
            continue
        row = {col: ("" if raw.get(col) is None else str(raw.get(col)).strip()) for col in columns}
        for col in columns:
            if not row[col] and col not in optional:
                errors.append(f"row {i}: {col} is required")
        for col in NUMBER_COLUMNS[kind]:
            if not row[col]:
                continue
            if not _number_ok(row[col]):
                errors.append(f"row {i}: {col} must be a number, got {row[col]!r}")
                continue
            row[col] = _normalise_number(row[col])
            if col in INTEGER_COLUMNS[kind]:
                if not _INTEGER.match(row[col]):
                    errors.append(f"row {i}: {col} must be a whole number of years, got {row[col]!r}")
                continue
            bare = not row[col].endswith("%")
            value = _fraction(row[col])
            low, high = VALUE_RANGE[col]
            if col in FRACTION_IF_BARE and bare and not -1.0 <= value <= 1.0:
                errors.append(f"row {i}: {col} {row[col]!r} is not a fraction; write it as a percent such as {row[col]}%")
            elif low is not None and value < low or high is not None and value > high:
                bounds = {"real_loss_prob": "between 0 and 1 (or 0%-100%)", "volatility": "not negative"}.get(
                    col, "between -1 and 1" if col != "expected_return" else "at least -100%")
                errors.append(f"row {i}: {col} must be {bounds}")
        for col in ASSET_CLASS_COLUMNS[kind]:
            if row[col] and canonical_asset_class(row[col]) not in _BASE_ASSET_CLASSES:
                errors.append(f"row {i}: {col} is not a known asset class: {row[col]!r}")
        if "preset" in columns and row["preset"] and row["preset"].upper() not in CAPITAL_MARKET_PRESETS:
            errors.append(f"row {i}: preset must be one of {', '.join(sorted(CAPITAL_MARKET_PRESETS))}")
        clean.append({col: row[col] for col in columns if row[col]})
    if skipped_blank and not clean and not errors:
        errors.append("every row is empty; fill a row in, or post an empty list to clear the table")
    if errors:
        raise OverrideRowsError(errors)
    return clean


def replace_rows(store: Any, kind: str, rows: Iterable[Mapping[str, str]]) -> int:
    """Replace table ``kind`` in the open, writable plan ``store`` with ``rows`` (already
    validated; call inside the caller's edit transaction). Rows whose cells are all empty are
    skipped without using up a ``row_N`` number. An empty list clears the table; a list holding
    only empty rows is refused (:class:`OverrideRowsError`) and the table is left as it was.
    Returns the number of rows written."""
    section = SECTIONS[kind]
    given = list(rows)
    kept = [row for row in given if not _is_blank_row(row, COLUMNS[kind])]
    if given and not kept:
        raise OverrideRowsError(["every row is empty; fill a row in, or post an empty list to clear the table"])
    for old in store.rows(section):
        store.delete_row(old["row_id"])
    count = 0
    for row in kept:
        count += 1
        for col in COLUMNS[kind]:
            if col in row and str(row[col]).strip():
                store.insert_row(section, subsection=f"row_{count}", label=col, value=str(row[col]).strip(), units=UNITS)
    return count
