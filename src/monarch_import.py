from __future__ import annotations

"""Monarch Extractor output -> internal transaction schema mapping.

The Monarch Extractor is a separate system (its source lives at
../Monarch Extractor, referenced relative to the workspace root -- see that
folder's monarch_extract.py) that writes an outbox of pending transaction
events to its own output folder. Confirmed against the real script
(2026-09-02):

- `output/new_transactions.csv` and `output/changed_transactions.csv` hold
  EVERY STILL-PENDING event across every past extractor run (not just the
  latest run), each tagged with a `run_id`. A downstream consumer must run
  `python monarch_extract.py --mark-delivered <run_id>` after successfully
  importing a run's events, or that run's rows keep reappearing in these
  files on every subsequent read (harmless to re-upsert, since upserting is
  idempotent, but the extractor's own delivery tracking never advances).
- `output/transactions.csv` (full history) and `output/duplicates_removed.csv`
  are NOT part of what a consumer should import -- the former is a
  convenience full dump (re-reading it would just reprocess every
  transaction ever seen), the latter is rows the extractor itself already
  excluded as duplicates.
- Fixed columns on every row: `id` (lowercase; Monarch's own stable
  transaction id), `date`, `merchant`, `amount`, `account`, `category`.
  Everything else is whatever extra columns Monarch's raw CSV export
  happened to contain (e.g. `original_statement`, `notes`, `tags`),
  normalized to a lowercase/underscored name -- present only if Monarch's
  own export included them, so treated as optional/best-effort here too.

This module maps those CSVs to the internal transaction shape
(`src.ytd_tracking.TRANSACTION_COLUMNS`) so `upsert_transactions_by_monarch_id()`
can merge them, and threads each row's `run_id` through so the caller can
call `--mark-delivered` once the upsert succeeds. It does not write
anything and does not invoke monarch_extract.py itself; see
src/monarch_autoimport_job.py for the end-to-end scheduled job.
"""

import csv
import io
import json
from pathlib import Path
from typing import Any

try:  # package import
    from . import ytd_tracking as ytd
except ImportError:  # pragma: no cover - direct execution fallback
    import ytd_tracking as ytd  # type: ignore

DEFAULT_FIELD_MAP_PATH = Path(__file__).with_name("monarch_field_map.json")

# Fallback used only if the shipped monarch_field_map.json is missing or
# unreadable -- keeps the importer functional (with the same placeholder
# guesses) rather than crashing on a missing/corrupt config file.
_FALLBACK_FIELD_MAP: dict[str, str] = {
    "id_column": "id",
    "date_column": "date",
    "merchant_column": "merchant",
    "category_column": "category",
    "account_column": "account",
    "original_statement_column": "original_statement",
    "notes_column": "notes",
    "amount_column": "amount",
    "tags_column": "tags",
    "owner_column": "owner",
    "run_id_column": "run_id",
}

# "_run_id" is not a src.ytd_tracking.TRANSACTION_COLUMNS field -- it rides
# along on each mapped row so the caller can collect the distinct run_ids it
# just imported and mark them delivered. normalize_transaction() (called
# inside upsert_transactions_by_monarch_id) only reads the real
# TRANSACTION_COLUMNS keys, so this extra key is silently ignored there.
_COLUMN_TO_MAP_KEY = {
    "Monarch Id": "id_column",
    "Date": "date_column",
    "Merchant": "merchant_column",
    "Category": "category_column",
    "Account": "account_column",
    "Original Statement": "original_statement_column",
    "Notes": "notes_column",
    "Amount": "amount_column",
    "Tags": "tags_column",
    "Owner": "owner_column",
    "_run_id": "run_id_column",
}

# The only two files a consumer should ever read from the Monarch Extractor's
# output folder -- see this module's docstring for why `transactions.csv`
# and `duplicates_removed.csv` are deliberately excluded.
CONSUMABLE_FILENAMES = ("new_transactions.csv", "changed_transactions.csv")


def load_field_map(path: str | Path | None = None) -> dict[str, str]:
    """Load the Monarch column-name mapping, falling back to built-in guesses."""
    candidate = Path(path) if path else DEFAULT_FIELD_MAP_PATH
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_FALLBACK_FIELD_MAP)
    merged = dict(_FALLBACK_FIELD_MAP)
    for key in _FALLBACK_FIELD_MAP:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def map_monarch_csv_text(text: str, field_map: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    """Map one Monarch CSV export's text to internal transaction rows.

    Returns (rows, errors). Rows are pre-normalize_transaction() dicts keyed
    by the internal TRANSACTION_COLUMNS names -- callers should pass them
    through upsert_transactions_by_monarch_id(), which normalizes internally.
    Column matching is case-insensitive/whitespace-tolerant, mirroring
    ytd_tracking.load_transactions_from_csv_text's tolerance for the manual
    upload path.
    """
    text = text or ""
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["CSV is empty or missing a header row."]
    header_by_lower = {str(h or "").strip().lower(): str(h or "") for h in reader.fieldnames}

    id_column = str(field_map.get("id_column") or "").strip().lower()
    if not id_column or id_column not in header_by_lower:
        return [], [
            f"CSV is missing the configured Monarch id column ('{field_map.get('id_column')}'). "
            f"Header received: {', '.join(reader.fieldnames)}. "
            "Update src/monarch_field_map.json's id_column to match, or fix the export."
        ]

    resolved: dict[str, str] = {}  # internal column -> actual CSV header
    for internal_col, map_key in _COLUMN_TO_MAP_KEY.items():
        configured = str(field_map.get(map_key) or "").strip().lower()
        if configured and configured in header_by_lower:
            resolved[internal_col] = header_by_lower[configured]

    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {internal_col: str(raw.get(source_header, "") or "").strip() for internal_col, source_header in resolved.items()}
        if not row.get("Monarch Id"):
            continue  # a row Monarch itself didn't give an id for cannot be upserted safely
        rows.append(row)
    return rows, []


def read_monarch_output_folder(source_dir: str | Path, field_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Read and map the two pending-event files in source_dir.

    Reads only CONSUMABLE_FILENAMES (new_transactions.csv,
    changed_transactions.csv) -- never transactions.csv (full history) or
    duplicates_removed.csv. A file that doesn't exist yet (e.g. no changed
    transactions this cycle) is skipped, not an error.

    Returns {"rows": [...], "files_consumed": [...], "run_ids": [...], "errors": {filename: [..]}}.
    A file with mapping errors contributes no rows but does not stop the
    other file from being read. "run_ids" is the sorted set of distinct
    Monarch run_ids found across every consumed row -- the caller marks each
    one delivered (via monarch_extract.py --mark-delivered) after a
    successful upsert.
    """
    field_map = field_map or load_field_map()
    root = Path(source_dir)
    rows: list[dict[str, str]] = []
    files_consumed: list[str] = []
    errors: dict[str, list[str]] = {}
    if not root.exists():
        return {"rows": rows, "files_consumed": files_consumed, "run_ids": [], "errors": {"": [f"Source folder does not exist: {root}"]}}
    for name in CONSUMABLE_FILENAMES:
        path = root / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            errors[name] = [f"Could not read file: {exc}"]
            continue
        mapped, file_errors = map_monarch_csv_text(text, field_map)
        if file_errors:
            errors[name] = file_errors
            continue
        rows.extend(mapped)
        files_consumed.append(name)
    run_ids = sorted({row["_run_id"] for row in rows if row.get("_run_id")})
    return {"rows": rows, "files_consumed": files_consumed, "run_ids": run_ids, "errors": errors}
