"""projection_tables.json: the Net Worth and Cash Flow projection tables as JSON, for the Financial
Trends reporter's Recent Projections view.

Read back from the worksheets build_sheet5/6 just wrote (never recomputed), so the JSON and the
workbook can't disagree. Columns carry the builders' semantic keys (``PreTax_1``, ``Σ_Inc``), which
never contain an owner's name, so the reporter's grouping survives renames and new accounts.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

FILE_NAME = "projection_tables.json"
SCHEMA = "projection_tables/1"

_AGE_KEYS = ("H Age", "W Age", "H_Age", "W_Age")
_SKIP_KEYS = frozenset({"Year", *_AGE_KEYS})
_TOTAL_KEYS = frozenset({"TOTAL NW", "Total_Tax", "Total_Cash_Need", "NW_Check"})


def _banners(ws) -> dict[int, str]:
    """Column number -> the row-1 group banner covering it (merged banners cover every column they span)."""
    out: dict[int, str] = {}
    for col in range(1, ws.max_column + 1):
        value = ws.cell(1, col).value
        if value not in (None, ""):
            out[col] = str(value)
    for rng in ws.merged_cells.ranges:
        if rng.min_row == 1:
            text = ws.cell(1, rng.min_col).value
            for col in range(rng.min_col, rng.max_col + 1):
                out[col] = str(text or "")
    return out


def _finite(v):
    """A JSON-safe cell value: NaN/inf become None (a browser rejects NaN in JSON)."""
    return None if isinstance(v, float) and not math.isfinite(v) else v


def table_from_sheet(ws, col_map: dict[str, int], *, data_first_row: int = 3) -> dict[str, Any]:
    """The projection table on ``ws`` as ``{"columns": [...], "rows": [...]}``.

    Rows stop at the first row whose column A is not an int year (the sheet's totals and summary
    blocks follow the data). Ages go into each row's ``ages``, not into ``columns``."""
    banners = _banners(ws)
    keyed = sorted(((col, key) for key, col in col_map.items() if key not in _SKIP_KEYS))
    columns = [{"key": key, "label": ws.cell(2, col).value, "banner": banners.get(col, ""),
                "subtotal": key.startswith("Σ") or key in _TOTAL_KEYS} for col, key in keyed]
    age_cols = [col_map[k] for k in _AGE_KEYS if k in col_map]
    rows = []
    r = data_first_row
    while True:
        year = ws.cell(r, 1).value
        if isinstance(year, bool) or not isinstance(year, int):
            break
        rows.append({"year": year, "ages": [ws.cell(r, col).value for col in age_cols],
                     "values": {key: _finite(ws.cell(r, col).value) for col, key in keyed}})
        r += 1
    return {"columns": columns, "rows": rows}


# Engine lines inside the NW sheet's TOTAL that the sheet has no column for (its TOTAL NW is
# ann + pre-tax + roth + trust + CST + HSA + other - additional liabilities; the sheet shows the
# liabilities itself as Other_Liab). Added as derived columns, only when non-zero in some year,
# so the reporter's groups add up to TOTAL NW.
_UNSHOWN_NW = (
    ("CST", "Credit Shelter Trust", "cst_nw", 1.0),
)


def add_unshown_nw_lines(table: dict, rows: list[dict]) -> dict[str, Any]:
    """``table`` (from :func:`table_from_sheet` on the NW sheet) plus the unshown engine lines, by year."""
    by_year = {r.get("year"): r for r in rows}
    columns = list(table["columns"])
    out_rows = [{**r, "values": dict(r["values"])} for r in table["rows"]]
    for key, label, field, sign in _UNSHOWN_NW:
        vals = [sign * float((by_year.get(r["year"]) or {}).get(field) or 0.0) for r in out_rows]
        if not any(abs(v) > 0.005 for v in vals):
            continue
        columns.append({"key": key, "label": label, "banner": "OTHER ASSETS", "subtotal": False, "derived": True})
        for r, v in zip(out_rows, vals):
            r["values"][key] = v + 0.0   # never -0.0
    return {"columns": columns, "rows": out_rows}


def read_projection_tables(nw_ws, nw_cols, cf_ws, cf_cols, rows) -> dict | None:
    """Both tables read back from the just-written sheets, or None (with a warning) on any failure:
    Recent Projections must never fail the workbook build."""
    try:
        return {"net_worth": add_unshown_nw_lines(table_from_sheet(nw_ws, nw_cols), rows),
                "cash_flow": table_from_sheet(cf_ws, cf_cols)}
    except Exception as exc:  # noqa: BLE001 - Recent Projections only; the workbook carries on
        print(f"WARNING: projection tables not read back ({exc.__class__.__name__}: {exc}); "
              "Recent Projections will ask for a rebuild.")
        return None


def write_or_clear_projection_tables(out_dir: str | Path, tables: dict | None, *, build_id: str, built_at: str,
                                     owners: list[str]) -> Path | None:
    """Write this build's tables; with none (or a failed write) remove the previous build's file so
    the reporter can't show it beside the new workbook. Never raises."""
    try:
        if tables is not None:
            return write_projection_tables(out_dir, projection_tables_doc(
                tables["net_worth"], tables["cash_flow"], build_id=build_id, built_at=built_at, owners=owners))
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: {FILE_NAME} not written ({exc.__class__.__name__}: {exc}).")
    try:
        (Path(out_dir) / FILE_NAME).unlink(missing_ok=True)
    except OSError as exc:
        print(f"WARNING: stale {FILE_NAME} not removed ({exc}).")
    return None


def projection_tables_doc(nw: dict, cf: dict, *, build_id: str, built_at: str, owners: list[str]) -> dict[str, Any]:
    return {"schema": SCHEMA, "build_id": build_id, "built_at": built_at, "owners": list(owners),
            "tables": {"net_worth": nw, "cash_flow": cf}}


def write_projection_tables(out_dir: str | Path, doc: dict) -> Path:
    """Write ``doc`` to ``<out_dir>/projection_tables.json`` atomically (temp file, then rename)."""
    out_dir = Path(out_dir)
    final = out_dir / FILE_NAME
    fd, tmp = tempfile.mkstemp(prefix=".projection_tables.", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, allow_nan=False)
        os.replace(tmp, final)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return final
