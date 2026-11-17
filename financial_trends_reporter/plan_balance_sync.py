"""Mirror the active plan's Monarch balances into the Financial Insight balance store.

A remote (multi-user) user uploads Monarch CSVs into their plan file; the desktop reporter instead imports the
extractor's CSV into its own SQLite store. This module makes the reporter's store follow the plan, so every
chart reads the same account history the user uploaded. The plan is opened read-only; the store is the
reporter's own and sits beside the history log (per user, per plan).

The sync is cheap to call on every page load: it compares a stamp of the plan's latest accepted import with the
stamp stored beside the balances and does nothing when they match.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from .balance_store import connect, import_balance_rows

SOURCE = "plan"
_STAMP_SQL = "CREATE TABLE IF NOT EXISTS plan_sync (id INTEGER PRIMARY KEY CHECK (id = 1), stamp TEXT NOT NULL)"


def _plan_stamp(repo: Any) -> str | None:
    last = repo.last_import(ok_only=True)
    if last is None and repo.count() == 0:
        return None
    return f"{(last or {}).get('id')}:{repo.count()}:{repo.latest_date()}"


def sync(workspace: str | Path, db_path: str | Path) -> dict[str, Any]:
    """Bring ``db_path`` up to date with the active plan of ``workspace``. Never raises.

    Returns ``{"success": True, "status": "unchanged" | "ok" | "no_balances", ...}`` or
    ``{"success": False, "error": ...}`` when the plan cannot be read (missing, locked, older schema).
    """
    from src import active_plan  # noqa: PLC0415 - keeps the module import light

    try:
        with active_plan.read_only_plan_access(), active_plan.workspace_store(Path(workspace)) as store:
            repo = store.monarch
            stamp = _plan_stamp(repo)
            if stamp is None:
                return {"success": True, "status": "no_balances"}
            with closing(connect(db_path)) as conn:
                conn.execute(_STAMP_SQL)
                row = conn.execute("SELECT stamp FROM plan_sync WHERE id = 1").fetchone()
                if row is not None and row["stamp"] == stamp:
                    return {"success": True, "status": "unchanged"}
            rows = repo.all_balances()
    except Exception as exc:  # noqa: BLE001 - a plan that is missing, locked or older than the tables
        return {"success": False, "error": f"{exc.__class__.__name__}: {exc}"}
    result = import_balance_rows(db_path, rows, f"{SOURCE}:{stamp}", mirror=True)
    if result.get("success"):
        with closing(connect(db_path)) as conn, conn:
            conn.execute(_STAMP_SQL)
            conn.execute("INSERT INTO plan_sync (id, stamp) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET stamp = excluded.stamp",
                         (stamp,))
    return result
