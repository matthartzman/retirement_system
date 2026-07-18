from __future__ import annotations

"""Read-only import preview helpers for large CSV adapters.

These helpers intentionally do not write workspace files.  Server routes and the
browser UI can call them before a transaction or holdings import so the user sees
row counts, date ranges, duplicate candidates, and mapping warnings before the
current working copy changes.
"""

import csv
import io
from datetime import date
from pathlib import Path
from typing import Any

try:  # package import
    from . import ytd_tracking as ytd
except ImportError:  # pragma: no cover - direct execution fallback
    import ytd_tracking as ytd  # type: ignore

HOLDINGS_COLUMNS = ["account", "symbol", "purchase_date", "shares", "purchase_price", "lot_type", "note"]


def _csv_dict_rows(text: str, *, required_columns: list[str] | None = None) -> tuple[list[dict[str, str]], list[str], list[str]]:
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames:
        return [], [], ["CSV is empty or missing a header row."]
    header = [str(x or "").strip() for x in reader.fieldnames]
    errors: list[str] = []
    if required_columns:
        missing = [c for c in required_columns if c not in header]
        if missing:
            errors.append("CSV is missing required column(s): " + ", ".join(missing))
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {k: str(v or "").strip() for k, v in raw.items() if k is not None}
        if any(str(v or "").strip() for v in row.values()):
            rows.append(row)
    return rows, header, errors


def _date_range(rows: list[dict[str, Any]], field: str) -> dict[str, str | None]:
    dates = []
    for row in rows:
        parsed = ytd.parse_date(row.get(field))
        if parsed:
            dates.append(parsed)
    return {"earliest": ytd.format_date(min(dates) if dates else None), "latest": ytd.format_date(max(dates) if dates else None)}


def _load_known_categories(input_root: str | Path) -> set[str]:
    root = Path(input_root)
    known: set[str] = set()
    for name, columns in (
        ("spending_category_map.csv", ("category",)),
        ("client_spending_taxonomy.csv", ("label", "category_id")),
    ):
        path = root / name
        if not path.exists():
            continue
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    for col in columns:
                        value = str(row.get(col, "") or "").strip()
                        if value:
                            known.add(value.lower())
        except OSError:
            continue
    return known


def preview_ytd_transactions_import(input_root: str | Path, text: str, mode: str = "replace", *, today: date | None = None) -> dict[str, Any]:
    """Return a side-effect-free preview of a YTD transaction CSV import.

    All rows with a valid Date are counted as importable regardless of
    calendar year — full transaction history is retained so actuals can be
    viewed for either the current year-to-date or the prior calendar year.
    """
    incoming_all, errors = ytd.load_transactions_from_csv_text(text or "")
    current_year = today.year if today else date.today().year
    mode = str(mode or "replace").strip().lower()
    if errors:
        return {
            "success": False,
            "schema": "import_preview_v1",
            "kind": "ytd_transactions",
            "mode": mode,
            "errors": errors[:50],
            "received": len(incoming_all),
            "current_year": current_year,
            "will_write": False,
        }

    input_root = Path(input_root)
    existing = ytd.read_transactions(input_root, today=today)
    existing_hashes = {ytd.transaction_hash(r) for r in existing}
    seen_upload_hashes: set[str] = set()
    duplicate_existing = 0
    duplicate_within_upload = 0
    non_current_year = 0
    valid_current_year: list[dict[str, str]] = []
    invalid_date_rows = 0
    latest_existing = max([ytd.parse_date(r.get("Date")) for r in existing if ytd.parse_date(r.get("Date"))] or [None])
    skipped_by_incremental_window = 0

    for row in incoming_all:
        d = ytd.parse_date(row.get("Date"))
        if not d:
            invalid_date_rows += 1
            continue
        h = ytd.transaction_hash(row)
        if h in existing_hashes:
            duplicate_existing += 1
        if h in seen_upload_hashes:
            duplicate_within_upload += 1
        seen_upload_hashes.add(h)
        if mode not in {"replace", "reload", "delete_all_and_reload"} and latest_existing and d <= latest_existing:
            skipped_by_incremental_window += 1
        valid_current_year.append(row)

    if mode in {"replace", "reload", "delete_all_and_reload"}:
        rows_added = len(valid_current_year)
        rows_skipped = non_current_year + invalid_date_rows
        total_after = len(valid_current_year)
        rows_replaced = len(existing)
    else:
        would_add = 0
        hashes = set(existing_hashes)
        for row in valid_current_year:
            d = ytd.parse_date(row.get("Date"))
            h = ytd.transaction_hash(row)
            if latest_existing and d and d <= latest_existing:
                continue
            if h in hashes:
                continue
            hashes.add(h)
            would_add += 1
        rows_added = would_add
        rows_skipped = len(incoming_all) - would_add
        total_after = len(existing) + would_add
        rows_replaced = 0

    known_categories = _load_known_categories(input_root)
    incoming_categories = sorted({str(r.get("Category", "") or "").strip() for r in valid_current_year if str(r.get("Category", "") or "").strip()})
    unmapped = [cat for cat in incoming_categories if cat.lower() not in known_categories]
    current_accounts = {str(r.get("Account", "") or "").strip() for r in existing if str(r.get("Account", "") or "").strip()}
    upload_accounts = {str(r.get("Account", "") or "").strip() for r in valid_current_year if str(r.get("Account", "") or "").strip()}

    return {
        "success": True,
        "schema": "import_preview_v1",
        "kind": "ytd_transactions",
        "mode": mode,
        "will_write": False,
        "current_year": current_year,
        "received": len(incoming_all),
        "current_rows": len(existing),
        "valid_current_year_rows": len(valid_current_year),
        "rows_added": rows_added,
        "rows_replaced": rows_replaced,
        "rows_skipped": rows_skipped,
        "total_after": total_after,
        "date_range": _date_range(valid_current_year, "Date"),
        "duplicate_candidates": {
            "matching_existing_rows": duplicate_existing,
            "within_upload_rows": duplicate_within_upload,
            "total": duplicate_existing + duplicate_within_upload,
        },
        "incremental_window_skips": skipped_by_incremental_window,
        "skipped_not_current_year": non_current_year,
        "invalid_date_rows": invalid_date_rows,
        "account_summary": {
            "incoming_accounts": sorted(upload_accounts),
            "new_accounts": sorted(upload_accounts - current_accounts),
        },
        "unmapped_categories": unmapped[:100],
        "unmapped_category_count": len(unmapped),
        "warnings": _ytd_preview_warnings(non_current_year, duplicate_existing + duplicate_within_upload, len(unmapped), skipped_by_incremental_window, mode),
    }


def _ytd_preview_warnings(non_current_year: int, duplicate_count: int, unmapped_count: int, incremental_window_skips: int, mode: str) -> list[str]:
    warnings: list[str] = []
    if non_current_year:
        warnings.append(f"{non_current_year} row(s) are outside the current reporting year and will be skipped.")
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate candidate row(s) were detected before import.")
    if unmapped_count:
        warnings.append(f"{unmapped_count} incoming categor{'y is' if unmapped_count == 1 else 'ies are'} not currently mapped in spending categories.")
    if mode not in {"replace", "reload", "delete_all_and_reload"} and incremental_window_skips:
        warnings.append(f"{incremental_window_skips} row(s) are on or before the latest existing transaction date and will be skipped in incremental mode.")
    return warnings


def _safe_float(value: Any) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        if text == "":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _holding_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("account", "") or "").strip().lower(),
        str(row.get("symbol", "") or "").strip().upper(),
        ytd.format_date(ytd.parse_date(row.get("purchase_date"))) or str(row.get("purchase_date", "") or "").strip(),
        str(row.get("shares", "") or "").replace(",", "").strip(),
        str(row.get("purchase_price", "") or "").replace("$", "").replace(",", "").strip(),
    )


def _symbol_set(rows: list[dict[str, str]]) -> set[str]:
    return {str(r.get("symbol", "") or "").strip().upper() for r in rows if str(r.get("symbol", "") or "").strip()}


def _load_security_master_symbols(project_root: str | Path) -> set[str]:
    root = Path(project_root)
    path = root / "reference_data" / "security_master.csv"
    if not path.exists():
        return set()
    symbols: set[str] = set()
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                sym = str(row.get("symbol", "") or row.get("Symbol", "") or "").strip().upper()
                if sym:
                    symbols.add(sym)
    except OSError:
        pass
    return symbols


def preview_holdings_import(current_text: str, incoming_text: str, *, project_root: str | Path | None = None, mode: str = "replace") -> dict[str, Any]:
    """Return a side-effect-free preview of a holdings CSV import."""
    incoming_rows, header, errors = _csv_dict_rows(incoming_text or "", required_columns=["account", "symbol", "shares", "purchase_price"])
    current_rows, _current_header, _current_errors = _csv_dict_rows(current_text or "", required_columns=["account", "symbol", "shares", "purchase_price"])
    mode = str(mode or "replace").strip().lower()
    if errors:
        return {
            "success": False,
            "schema": "import_preview_v1",
            "kind": "holdings",
            "mode": mode,
            "header": header,
            "errors": errors[:50],
            "received": len(incoming_rows),
            "will_write": False,
        }

    existing_keys = {_holding_key(r) for r in current_rows}
    seen_upload_keys: set[tuple[str, str, str, str, str]] = set()
    duplicate_existing = 0
    duplicate_within_upload = 0
    invalid_share_rows = 0
    invalid_price_rows = 0
    missing_account_rows = 0
    missing_symbol_rows = 0
    date_warnings = 0
    total_market_value = 0.0
    accounts: set[str] = set()

    for row in incoming_rows:
        account = str(row.get("account", "") or "").strip()
        symbol = str(row.get("symbol", "") or "").strip().upper()
        if not account:
            missing_account_rows += 1
        else:
            accounts.add(account)
        if not symbol:
            missing_symbol_rows += 1
        shares = _safe_float(row.get("shares"))
        price = _safe_float(row.get("purchase_price"))
        if shares is None:
            invalid_share_rows += 1
        if price is None:
            invalid_price_rows += 1
        if shares is not None and price is not None:
            total_market_value += shares * price
        if row.get("purchase_date") and not ytd.parse_date(row.get("purchase_date")):
            date_warnings += 1
        key = _holding_key(row)
        if key in existing_keys:
            duplicate_existing += 1
        if key in seen_upload_keys:
            duplicate_within_upload += 1
        seen_upload_keys.add(key)

    current_accounts = {str(r.get("account", "") or "").strip() for r in current_rows if str(r.get("account", "") or "").strip()}
    incoming_symbols = _symbol_set(incoming_rows)
    known_symbols = _load_security_master_symbols(project_root or Path.cwd())
    symbols_not_in_master = sorted(s for s in incoming_symbols if s not in known_symbols and s != "CASH") if known_symbols else []
    warnings: list[str] = []
    if duplicate_existing or duplicate_within_upload:
        warnings.append(f"{duplicate_existing + duplicate_within_upload} duplicate candidate lot(s) were detected before import.")
    if missing_account_rows or missing_symbol_rows:
        warnings.append(f"{missing_account_rows + missing_symbol_rows} row(s) are missing account or symbol values.")
    if invalid_share_rows or invalid_price_rows:
        warnings.append(f"{invalid_share_rows + invalid_price_rows} row(s) have missing or non-numeric share/price values.")
    if date_warnings:
        warnings.append(f"{date_warnings} row(s) have purchase dates that could not be normalized.")
    if symbols_not_in_master:
        warnings.append(f"{len(symbols_not_in_master)} symbol(s) are not in security_master.csv; pricing may fall back to cache/provider behavior.")

    rows_added = len(incoming_rows) if mode in {"replace", "reload", "delete_all_and_reload"} else max(0, len(incoming_rows) - duplicate_existing - duplicate_within_upload)
    total_after = len(incoming_rows) if mode in {"replace", "reload", "delete_all_and_reload"} else len(current_rows) + rows_added

    return {
        "success": True,
        "schema": "import_preview_v1",
        "kind": "holdings",
        "mode": mode,
        "will_write": False,
        "header": header,
        "received": len(incoming_rows),
        "current_rows": len(current_rows),
        "rows_added": rows_added,
        "rows_replaced": len(current_rows) if mode in {"replace", "reload", "delete_all_and_reload"} else 0,
        "total_after": total_after,
        "date_range": _date_range(incoming_rows, "purchase_date"),
        "duplicate_candidates": {
            "matching_existing_rows": duplicate_existing,
            "within_upload_rows": duplicate_within_upload,
            "total": duplicate_existing + duplicate_within_upload,
        },
        "account_summary": {
            "incoming_accounts": sorted(accounts),
            "new_accounts": sorted(accounts - current_accounts),
        },
        "symbol_summary": {
            "incoming_symbols": sorted(incoming_symbols),
            "symbols_not_in_security_master": symbols_not_in_master[:100],
        },
        "data_quality": {
            "missing_account_rows": missing_account_rows,
            "missing_symbol_rows": missing_symbol_rows,
            "invalid_share_rows": invalid_share_rows,
            "invalid_price_rows": invalid_price_rows,
            "unparseable_date_rows": date_warnings,
        },
        "estimated_cost_basis": round(total_market_value, 2),
        "warnings": warnings,
    }
