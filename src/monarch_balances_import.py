from __future__ import annotations

"""Import the Monarch Extractor's ``output/balances.csv`` into the plan file (schema v13).

Runs after the transaction import in the 04:00 job (``monarch_autoimport_job.run``). The extractor's
file is the normalized form of Monarch's balance history (``date,account_key,account,balance``, ISO
dates, full history every run), so an import is an idempotent upsert by (date, account_key).

A file that fails a guard is rejected, recorded in ``monarch_balance_imports`` and never written, so a
partial or changed export cannot corrupt the history: wrong header, an unreadable value, a latest date
older than yesterday, or an account count more than 20% below the last accepted import.
"""

import csv
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import active_plan, platform_runtime

EXPECTED_HEADER = ["date", "account_key", "account", "balance"]
MAX_ACCOUNT_DROP = 0.20


def default_source_path(base_dir: str | Path) -> Path:
    """The extractor's output file; pinned to the one place the app ships the extractor."""
    return Path(base_dir) / "Monarch Extractor" / "output" / "balances.csv"


def read_balances_csv(path: Path) -> list[tuple[str, str, str, float]]:
    """Parse and validate the extractor's balances file; raises ValueError on any problem."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if [h.strip() for h in (header or [])] != EXPECTED_HEADER:
            raise ValueError(f"unexpected balances header {header!r}")
        rows: list[tuple[str, str, str, float]] = []
        for line_no, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != 4:
                raise ValueError(f"line {line_no}: expected 4 columns, got {len(row)}")
            try:
                iso = date.fromisoformat(row[0]).isoformat()
                balance = float(row[3])
            except ValueError as exc:
                raise ValueError(f"line {line_no}: {exc}") from None
            if not math.isfinite(balance):
                raise ValueError(f"line {line_no}: non-finite balance")
            if not row[1] or not row[2]:
                raise ValueError(f"line {line_no}: empty account")
            rows.append((iso, row[1], row[2], balance))
    if not rows:
        raise ValueError("balances file contained no rows")
    return rows


def import_balances(base_dir: str | Path, csv_path: str | Path | None = None, *, today: date | None = None,
                    now: datetime | None = None) -> dict[str, Any]:
    """Validate and upsert one balances file into the plan of workspace ``base_dir``.

    Never raises for bad input; returns ``{"success": bool, "status": "ok"|"rejected"|"skipped", ...}``.
    A missing file is a quiet skip (the extractor has not produced balances yet), not a rejection.
    """
    path = Path(csv_path) if csv_path else default_source_path(base_dir)
    if not path.is_file():
        return {"success": True, "status": "skipped", "skip_reason": "no balances file"}
    today = today or platform_runtime.today()
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    with active_plan.workspace_store(base_dir, write=True) as store:
        repo = store.monarch

        def reject(reason: str) -> dict[str, Any]:
            repo.record_import(stamp, str(path), "rejected", detail=reason)
            return {"success": False, "status": "rejected", "error": reason}

        try:
            rows = read_balances_csv(path)
        except (ValueError, OSError) as exc:
            return reject(str(exc))
        keys = {r[1] for r in rows}
        latest = max(r[0] for r in rows)
        if date.fromisoformat(latest) < today - timedelta(days=1):
            return reject(f"stale export: latest date {latest} is older than yesterday ({today - timedelta(days=1)})")
        prev = repo.last_import(ok_only=True)
        if prev and prev["accounts"] and len(keys) < prev["accounts"] * (1 - MAX_ACCOUNT_DROP):
            return reject(f"account count fell from {prev['accounts']} to {len(keys)} (more than {int(MAX_ACCOUNT_DROP * 100)}% drop)")
        with store.transaction():
            renamed = repo.migrate_renames(rows)
            repo.upsert_balances(rows)
            repo.record_import(stamp, str(path), "ok", rows=len(rows), accounts=len(keys), latest_date=latest,
                               detail="; ".join(f"renamed {old!r} -> {new!r}" for old, new in renamed))
    return {"success": True, "status": "ok", "rows": len(rows), "accounts": len(keys), "latest_date": latest,
            "renamed": renamed}
