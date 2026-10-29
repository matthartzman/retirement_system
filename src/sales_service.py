"""Realized-sales ledger, server side of the Sales ledger page: manual entry, CSV import (preview, then
commit) and the ledger list. Validation and derived fields come from ``sales_ledger``; storage is the plan
file's ``store.sales`` (``SalesRepo``). Every function takes the workspace ``input`` folder like ``reconcile``.

Manual and CSV rows are one lot (or part of a lot) each, with the lot's basis and purchase date typed in.
Nothing reads the ledger yet (Phase 1)."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from . import active_plan
from .sales_ledger import ValidationError, validate_sale_row

CSV_REQUIRED = ("sale_date", "account", "tax_class", "symbol", "shares", "proceeds", "basis")
CSV_COLUMNS = CSV_REQUIRED + ("fees", "purchase_date")
_NUMERIC = ("shares", "proceeds", "fees", "basis")


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _key(row: dict[str, Any]) -> tuple:
    return (row["sale_date"], row["account"], row["symbol"], round(float(row["shares"]), 6),
            row.get("purchase_date") or "", round(float(row["proceeds"]), 2), round(float(row["basis"]), 2))


def _manual(row: dict[str, Any]) -> dict[str, Any]:
    allowed = set(CSV_COLUMNS) | {"settle_date", "wash_note", "lot_key"}
    return validate_sale_row({**{k: v for k, v in row.items() if k in allowed}, "source": "manual"})


def _existing_keys(store) -> set[tuple]:
    return {_key(r) for r in store.sales.list_sales()}


def add_sale(input_dir: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    """Record one manual sale; returns the stored row. Raises ``ValidationError`` and writes nothing on a bad row."""
    clean = _manual(row)
    clean.pop("status", None)
    with active_plan.workspace_store(_base(input_dir), write=True) as store:
        return store.sales.get_sale(store.sales.insert_sale(**clean))


def list_sales(input_dir: str | Path, *, year: int | None = None, include_voided: bool = False) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        sales = store.sales.list_sales(year=year, include_voided=include_voided)
    live = [s for s in sales if s["status"] == "confirmed" and s["gain"] is not None]
    return {"sales": sales, "totals": {
        "count": len(sales),
        "short_gain": sum(s["gain"] for s in live if s["holding_period"] == "short"),
        "long_gain": sum(s["gain"] for s in live if s["holding_period"] == "long"),
    }}


def _set_voided(input_dir: str | Path, sale_id: int, voided: bool) -> None:
    try:
        with active_plan.workspace_store(_base(input_dir), write=True) as store:
            (store.sales.void_sale if voided else store.sales.unvoid_sale)(int(sale_id))
    except active_plan.StoreError as exc:
        raise ValidationError(str(exc)) from exc


def void_sale(input_dir: str | Path, sale_id: int) -> None:
    _set_voided(input_dir, sale_id, True)


def unvoid_sale(input_dir: str | Path, sale_id: int) -> None:
    _set_voided(input_dir, sale_id, False)


def _parse_csv(text: str) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    """(line, validated row) pairs and per-line errors. A missing column is one error for the file."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    header = [str(h or "").strip() for h in (reader.fieldnames or [])]
    missing = [c for c in CSV_REQUIRED if c not in header]
    if missing:
        return [], [{"line": 1, "error": "CSV is missing required column(s): " + ", ".join(missing)}]
    good, errors = [], []
    for line, raw in enumerate(reader, start=2):
        row = {str(k).strip(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(row.values()):
            continue
        try:
            for name in _NUMERIC:
                if row.get(name, "") != "":
                    try:
                        row[name] = float(row[name].replace(",", "").replace("$", ""))
                    except ValueError:
                        raise ValidationError(f"{name} must be a number, got {row[name]!r}") from None
                else:
                    row.pop(name, None)
            good.append((line, _manual(row)))
        except ValidationError as exc:
            errors.append({"line": line, "error": str(exc)})
    return good, errors


def preview_csv(input_dir: str | Path, text: str) -> dict[str, Any]:
    """Side-effect-free ``import_preview_v1``-style report: ``received``, ``will_write``, ``duplicates`` (already in the
    ledger or repeated in the file), ``errors`` (line number and reason)."""
    good, errors = _parse_csv(text)
    with active_plan.workspace_store(_base(input_dir)) as store:
        seen = _existing_keys(store)
    will_write, duplicates = [], []
    for line, row in good:
        k = _key(row)
        (duplicates if k in seen else will_write).append({**row, "line": line} if k in seen else row)
        seen.add(k)
    return {"received": len(good) + len(errors), "will_write": will_write, "duplicates": duplicates, "errors": errors}


def commit_csv(input_dir: str | Path, text: str) -> dict[str, Any]:
    """Write the preview's ``will_write`` rows in one transaction. Any bad line refuses the whole file."""
    good, errors = _parse_csv(text)
    if errors:
        raise ValidationError("; ".join(f"line {e['line']}: {e['error']}" for e in errors))
    written = 0
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        seen = _existing_keys(store)
        for _, row in good:
            if _key(row) in seen:
                continue
            row.pop("status", None)
            store.sales.insert_sale(**row)
            seen.add(_key(row))
            written += 1
    return {"written": written, "skipped_duplicates": len(good) - written}
