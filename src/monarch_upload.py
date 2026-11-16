from __future__ import annotations

"""Monarch's own CSV exports, uploaded from the browser, into the existing import shapes (multi-user Phase 4).

A remote user cannot run the Monarch Extractor (it drives a visible browser on the server), so they download
Monarch's exports themselves and upload them: Transactions > Download CSV, and the account balance history.
Design: ``documentation/future/multi-user-server-monarch-secrets-design.md`` section 1.

The two normalisers here re-implement, on text, the extractor's ``monarch_extract.normalize_transaction`` /
``clean_key`` and ``monarch_balances.normalize_balances_csv``. They are not imported: the extractor folder is not
a package, is not part of an installed or frozen worker, and its functions take file paths. A parity test loads
the extractor by path and compares the two on the same input.

Transactions go through ``monarch_import.map_monarch_csv_text`` (the shipped field map) and
``ytd_tracking.upsert_transactions_by_monarch_id``; balances through ``monarch_balances_import.import_balance_rows``
(the same guards as the extractor import). Nothing is written to disk except through the plan store. Every
account name and message in a response or log line is masked (:func:`mask_names`).
"""

import base64
import binascii
import csv
import io
import logging
import math
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import account_numbers
from .csv_exchange import text_csv as _tcsv

LOG = logging.getLogger("retirement_system.monarch_upload")

KINDS = ("transactions", "balances")
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 250_000
MAX_NAMES = 200
# Where provisioning puts the admin-curated mapping CSV inside a user's workspace (gateway --monarch-mapping-csv).
MAPPING_SEED_RELPATH = Path("local_state") / "monarch_mapping_seed.csv"

MONARCH_ID_HEADER = "Id"
TX_REQUIRED = ("Date", "Account", "Amount", MONARCH_ID_HEADER)
BAL_HEADER = ["Date", "Balance", "Account"]
_EXTRACTOR_COLUMNS = ["id", "date", "merchant", "amount", "account", "category"]
_LONG_RUN = re.compile(r"\d{5,}")
_BOM = "﻿"


class UploadError(ValueError):
    """The upload was refused; the message is masked and safe to show the user."""


def mask_names(text: object) -> str:
    """Cue-based account-number masking, then any remaining run of 5+ digits as ``…NNNN``."""
    out = account_numbers.mask_text("" if text is None else str(text))
    return _LONG_RUN.sub(lambda m: account_numbers.ELLIPSIS + m.group(0)[-4:], out)


def _refuse(message: str) -> UploadError:
    return UploadError(mask_names(message))


# ---------------------------------------------------------------- decoding

def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise _refuse("The file is not UTF-8 or Windows-1252 text.")


def decode_upload(body: Any) -> tuple[str, str, bool]:
    """``(kind, text, dry_run)`` from the JSON body, or :class:`UploadError`."""
    if not isinstance(body, dict):
        raise _refuse("A JSON object body is required.")
    kind = str(body.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise _refuse(f"kind must be one of {', '.join(KINDS)}.")
    raw = body.get("content_base64")
    if not isinstance(raw, str):
        raise _refuse("content_base64 is required (the file's bytes, base64-encoded).")
    if len(raw) > (MAX_BYTES * 4) // 3 + 8:
        raise _refuse(f"The file is too large (limit {MAX_BYTES // (1024 * 1024)} MiB).")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise _refuse("content_base64 is not valid base64.") from None
    if len(data) > MAX_BYTES:
        raise _refuse(f"The file is too large (limit {MAX_BYTES // (1024 * 1024)} MiB).")
    if not data.strip():
        raise _refuse("The file is empty.")
    return kind, _decode_text(data), bool(body.get("dry_run"))


def _rows(text: str) -> tuple[list[str], list[list[str]]]:
    """Header and non-blank rows. Streams the reader and counts every physical row, blank ones too, so a file
    of newlines cannot build a huge list; a malformed field (too large, NUL) is a refusal, not a server error."""
    header: list[str] | None = None
    rows: list[list[str]] = []
    physical = 0
    try:
        for row in csv.reader(io.StringIO(text.lstrip(_BOM))):
            physical += 1
            if physical > 2 * MAX_ROWS:
                raise _refuse(f"The file has more than {MAX_ROWS:,} rows.")
            if header is None:
                header = row
                continue
            if not row or not any(cell.strip() for cell in row):
                continue
            rows.append(row)
            if len(rows) > MAX_ROWS:
                raise _refuse(f"The file has more than {MAX_ROWS:,} rows.")
    except csv.Error:
        raise _refuse("The file is not valid CSV (a field is too large or malformed).") from None
    return [h.strip() for h in (header or [])], rows


# ---------------------------------------------------------------- transactions (monarch_extract parity)

def _clean_key(value: object) -> str:
    text = str(value).strip()
    return "".join(c if c.isalnum() or c == "_" else "_" for c in text).strip("_").lower()


def _clean_value(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_transactions_text(text: str) -> list[dict[str, Any]]:
    """Raw Monarch transaction export -> the extractor's normalised transactions (one dict per row)."""
    header, rows = _rows(text)
    lower = {h.casefold() for h in header}
    if [h.casefold() for h in header] == [h.casefold() for h in BAL_HEADER]:
        raise _refuse("This looks like a balances export; upload it with kind \"balances\".")
    missing = [h for h in TX_REQUIRED if h.casefold() not in lower]
    if missing:
        raise _refuse(f"The transactions export is missing the column(s) {', '.join(missing)}. Use Monarch's "
                      "Transactions > Download CSV (it includes Monarch's own Id column).")
    out = []
    for row in rows:
        original = {h: _clean_value(row[i]) if i < len(row) else "" for i, h in enumerate(header) if h}
        source_columns = {_clean_key(k): v for k, v in original.items() if _clean_key(k)}
        monarch_id = next((v for k, v in original.items() if k.casefold() == MONARCH_ID_HEADER.casefold()), "")
        out.append({
            "id": monarch_id,
            "date": original.get("Date", ""),
            "merchant": original.get("Merchant") or original.get("Name") or "",
            "amount": original.get("Amount", ""),
            "account": original.get("Account", ""),
            "category": original.get("Category", ""),
            "source_columns": source_columns,
        })
    if not out:
        raise _refuse("The transactions export has no rows.")
    return out


def _extractor_csv(transactions: list[dict[str, Any]]) -> str:
    """The transactions as the extractor's outbox CSV text (fixed columns, then the cleaned extra columns)."""
    extra = sorted({k for t in transactions for k in t["source_columns"]} - set(_EXTRACTOR_COLUMNS))
    return _tcsv.rows_to_text([_EXTRACTOR_COLUMNS + extra] + [
        [t[c] for c in _EXTRACTOR_COLUMNS] + [t["source_columns"].get(c, "") for c in extra] for t in transactions])


def import_transaction_rows(base_dir: str | Path, transactions: list[dict[str, Any]], *,
                            dry_run: bool = False) -> dict[str, Any]:
    """Normalised transactions -> ``ytd_transactions`` (upsert by Monarch id). The connector seam uses this too."""
    from . import monarch_import as mi
    from . import ytd_tracking as ytd

    with_id = [t for t in transactions if t["id"]]
    by_id: dict[str, dict[str, Any]] = {}
    for t in with_id:
        by_id[t["id"]] = t  # a later row of the same id wins, as in the extractor's history
    unique = list(by_id.values())
    dates = sorted(t["date"] for t in unique if t["date"])
    names = sorted({t["account"] for t in unique if t["account"]})
    result: dict[str, Any] = {
        "rows_read": len(transactions), "rows_without_id": len(transactions) - len(with_id),
        "duplicates_in_file": len(with_id) - len(unique), "date_range": [dates[0], dates[-1]] if dates else [],
        "accounts": len(names), "account_names": [mask_names(n) for n in names[:MAX_NAMES]],
        "added": 0, "updated": 0, "adopted": 0, "skipped": 0,
    }
    if not unique:
        raise _refuse("No row has a Monarch Id, so nothing can be imported safely.")
    mapped, errors = mi.map_monarch_csv_text(_extractor_csv(unique), mi.load_field_map())
    if errors:
        raise _refuse("; ".join(errors))
    if dry_run:
        return result
    upsert = ytd.upsert_transactions_by_monarch_id(Path(base_dir) / "input", mapped)
    for key in ("added", "updated", "adopted", "skipped"):
        result[key] = int(upsert.get(key) or 0)
    return result


# ---------------------------------------------------------------- balances (monarch_balances parity)

def _clean_account_name(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def _parse_date(text: str) -> str:
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {text!r}")


def _parse_amount(text: str) -> float:
    text = (text or "").strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"unparseable balance {text!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"non-finite balance {text!r}")
    return value


def normalize_balances_text(text: str) -> list[tuple[str, str, str, float]]:
    """Raw Monarch balance history (``Date,Balance,Account``) -> sorted ``(date, account_key, account, balance)``."""
    header, rows = _rows(text)
    if header != BAL_HEADER:
        raise _refuse(f"The balances export must have the header {','.join(BAL_HEADER)}.")
    merged: dict[tuple[str, str], tuple[str, str, str, float]] = {}
    for line_no, row in enumerate(rows, start=2):
        if len(row) != 3:
            raise _refuse(f"line {line_no}: expected 3 columns, got {len(row)}")
        try:
            iso, amount = _parse_date(row[0]), _parse_amount(row[1])
        except ValueError as exc:
            raise _refuse(f"line {line_no}: {exc}") from None
        name = _clean_account_name(row[2])
        if not name:
            raise _refuse(f"line {line_no}: empty account name")
        key = (iso, name.casefold())
        if key in merged and merged[key][3] != amount:
            raise _refuse(f"line {line_no}: two accounts named {name!r} on {iso} with different balances; "
                          "rename one in Monarch so they can be told apart")
        merged[key] = (iso, name.casefold(), name, amount)
    if not merged:
        raise _refuse("The balances export has no rows.")
    return sorted(merged.values(), key=lambda r: (r[0], r[1]))


def _seed_counts(base: Path) -> dict[str, int] | None:
    seed = base / MAPPING_SEED_RELPATH
    if not seed.is_file():
        return None
    from . import monarch_mapping_seed

    try:
        report = monarch_mapping_seed.seed_mapping(base, csv_path=seed, overwrite=False)
    except Exception as exc:  # noqa: BLE001 - a bad seed file never fails an accepted import
        LOG.warning("Monarch mapping seed not applied: %s", mask_names(exc.__class__.__name__))
        return {"error": 1}
    return {k: len(v) for k, v in report.items()}


def import_balance_rows_for_upload(base_dir: str | Path, rows: list[tuple[str, str, str, float]], *,
                                   dry_run: bool = False, today: date | None = None,
                                   now: datetime | None = None, source: str = "browser upload",
                                   compare_same_source: bool = False) -> dict[str, Any]:
    """Normalised balances -> the plan's Monarch tables through the extractor import's guards, then the seed.
    The connector seam uses this too (``source="monarch connector"``, ``compare_same_source=True``)."""
    from . import monarch_balances_import as mbi

    base = Path(base_dir)
    names = sorted({r[2] for r in rows})
    summary: dict[str, Any] = {
        "rows": len(rows), "accounts": len({r[1] for r in rows}), "latest_date": rows[-1][0] if rows else "",
        "date_range": [rows[0][0], rows[-1][0]] if rows else [],
        "account_names": [mask_names(n) for n in names[:MAX_NAMES]],
    }
    if dry_run:
        return {"success": True, "status": "dry_run", **summary}
    out = mbi.import_balance_rows(base, rows, source=source, today=today, now=now,
                                  compare_same_source=compare_same_source)
    result = {**summary, "success": bool(out.get("success")), "status": out.get("status")}
    if out.get("status") != "ok":
        result["error"] = mask_names(out.get("error") or "rejected")
        return result
    result["renamed"] = [[mask_names(a), mask_names(b)] for a, b in out.get("renamed") or []]
    result["mapping_seed"] = _seed_counts(base)
    return result


# ---------------------------------------------------------------- the route's body

def handle_upload(base_dir: str | Path, body: Any, *, today: date | None = None,
                  now: datetime | None = None) -> tuple[dict[str, Any], int]:
    """``(payload, http status)`` for ``POST /api/monarch/upload``. Never raises for bad input."""
    try:
        kind, text, dry_run = decode_upload(body)
        if kind == "transactions":
            result = {"success": True, **import_transaction_rows(base_dir, normalize_transactions_text(text),
                                                                 dry_run=dry_run)}
        else:
            result = import_balance_rows_for_upload(base_dir, normalize_balances_text(text), dry_run=dry_run,
                                                    today=today, now=now)
    except UploadError as exc:
        return {"success": False, "error": str(exc)}, 400
    result.update({"kind": kind, "dry_run": dry_run})
    LOG.info("Monarch %s upload%s: %s rows, %s accounts, status %s", kind, " (dry run)" if dry_run else "",
             result.get("rows_read", result.get("rows")), result.get("accounts"), result.get("status", "ok"))
    return result, (200 if result.get("success") else 400)
