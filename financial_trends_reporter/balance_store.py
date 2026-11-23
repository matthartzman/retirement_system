from __future__ import annotations

"""Monarch daily account balances: SQLite store + guarded import.

The Monarch Extractor writes ``Monarch Extractor/output/balances.csv``
(``date,account_key,account,balance``, full history every run). This module
upserts it into ``data/monarch_balances.sqlite3`` keyed on (date, account_key),
so re-importing is idempotent and a re-download simply refreshes history.

Stdlib only (it runs under the extractor's own venv as well as the app's).
A file failing any guard is rejected and recorded in ``import_runs`` -- never
written -- so a partial or changed export cannot corrupt the history.
"""

import csv
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_FILENAME = "monarch_balances.sqlite3"
EXPECTED_HEADER = ["date", "account_key", "account", "balance"]
MAX_ACCOUNT_DROP = 0.20  # reject a file with >20% fewer accounts than the last good import

_SCHEMA = """
CREATE TABLE IF NOT EXISTS balances (
    date TEXT NOT NULL,
    account_key TEXT NOT NULL,
    balance REAL NOT NULL,
    PRIMARY KEY (date, account_key)
);
CREATE TABLE IF NOT EXISTS accounts (
    account_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    type TEXT,
    app_account TEXT,
    confirmed INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS account_prefs (
    chart TEXT NOT NULL,
    account_key TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    PRIMARY KEY (chart, account_key)
);
CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    accounts INTEGER NOT NULL DEFAULT 0,
    latest_date TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
"""


def default_db_path(app_root: str | Path) -> Path:
    return Path(app_root) / "data" / DB_FILENAME


def default_source_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "Monarch Extractor" / "output" / "balances.csv"


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # Phase 2 stores created before the registry lack ``confirmed``.
    if "confirmed" not in {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}:
        conn.execute("ALTER TABLE accounts ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    return conn


def _read_rows(csv_path: Path) -> list[tuple[str, str, str, float]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
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


def _detect_renames(conn: sqlite3.Connection, rows: list[tuple[str, str, str, float]]) -> list[tuple[str, str]]:
    """Old key -> new key for a Monarch rename. The export has no account id, so a rename arrives as a new
    key repeating a stored key's history (same dates and balances) while the old key is gone from the file.
    Mirrors ``MonarchRepo.migrate_renames`` in the app's plan store."""
    incoming: dict[str, dict[str, float]] = {}
    for d, key, _name, bal in rows:
        incoming.setdefault(key, {})[d] = bal
    stored: dict[str, dict[str, float]] = {}
    for r in conn.execute("SELECT date, account_key, balance FROM balances"):
        if r["account_key"] not in incoming:
            stored.setdefault(r["account_key"], {})[r["date"]] = r["balance"]
    # A key that is already confirmed or matched has been dealt with; only unreviewed ones can be a rename target.
    taken = {r["account_key"] for r in conn.execute("SELECT account_key FROM accounts WHERE confirmed=1 OR app_account IS NOT NULL")}
    candidates = {k: v for k, v in incoming.items() if k not in taken}
    moves: list[tuple[str, str]] = []
    for old, old_hist in stored.items():
        best, best_hits = None, 0
        for new, new_hist in candidates.items():
            hits = [d for d, b in old_hist.items() if d in new_hist and abs(new_hist[d] - b) < 0.005]
            if any(abs(old_hist[d]) >= 0.005 for d in hits) and len(hits) > best_hits:
                best, best_hits = new, len(hits)
        if best is None or best_hits < min(3, len(old_hist)) or best_hits < 0.8 * len(old_hist):
            continue
        candidates.pop(best)
        moves.append((old, best))
    return moves


def _move_account(conn: sqlite3.Connection, old: str, new: str) -> None:
    """Hand the old key's type, match and per-chart choices to the new key and drop the old key's history."""
    conn.execute(
        "UPDATE accounts SET type=(SELECT type FROM accounts WHERE account_key=?), "
        "app_account=(SELECT app_account FROM accounts WHERE account_key=?), "
        "confirmed=(SELECT confirmed FROM accounts WHERE account_key=?) WHERE account_key=?",
        (old, old, old, new))
    conn.execute("INSERT OR IGNORE INTO account_prefs (chart, account_key, enabled) "
                 "SELECT chart, ?, enabled FROM account_prefs WHERE account_key=?", (new, old))
    conn.execute("DELETE FROM account_prefs WHERE account_key=?", (old,))
    conn.execute("DELETE FROM balances WHERE account_key=?", (old,))
    conn.execute("DELETE FROM accounts WHERE account_key=?", (old,))


def _record(conn: sqlite3.Connection, now: datetime, source: Path | str, status: str, *, rows=0, accounts=0, latest=None, detail=None) -> None:
    conn.execute(
        "INSERT INTO import_runs (run_at, source_file, rows, accounts, latest_date, status, detail) VALUES (?,?,?,?,?,?,?)",
        (now.isoformat(timespec="seconds"), str(source), rows, accounts, latest, status, detail),
    )
    conn.commit()


def import_balances(db_path: str | Path, csv_path: str | Path, *, today: date | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Validate and upsert one balances file. Never raises for bad input."""
    csv_path = Path(csv_path)
    now = now or datetime.now(timezone.utc)
    with closing(connect(db_path)) as conn:
        if not csv_path.exists():
            return _reject(conn, now, csv_path, f"balances file not found: {csv_path}")
        try:
            rows = _read_rows(csv_path)
        except (ValueError, OSError) as exc:
            return _reject(conn, now, csv_path, str(exc))
        return _import_rows(conn, rows, str(csv_path), today=today or date.today(), now=now)


def import_balance_rows(db_path: str | Path, rows: list[tuple[str, str, str, float]], source: str, *,
                        now: datetime | None = None, mirror: bool = False) -> dict[str, Any]:
    """Upsert already-parsed ``(date, account_key, account, balance)`` rows. The staleness and account-drop guards are
    skipped: the caller's rows were accepted by the plan's own guarded import. ``mirror`` makes the store hold exactly
    these accounts: a key that is not in ``rows`` (and not a rename) is dropped with its history and preferences."""
    now = now or datetime.now(timezone.utc)
    with closing(connect(db_path)) as conn:
        return _import_rows(conn, rows, source, today=None, now=now, mirror=mirror)


def _reject(conn: sqlite3.Connection, now: datetime, source: str | Path, reason: str) -> dict[str, Any]:
    _record(conn, now, str(source), "rejected", detail=reason)
    return {"success": False, "status": "rejected", "error": reason}


def _import_rows(conn: sqlite3.Connection, rows: list[tuple[str, str, str, float]], source: str, *,
                 today: date | None, now: datetime, mirror: bool = False) -> dict[str, Any]:
    if not rows:
        return _reject(conn, now, source, "balances file contained no rows")
    keys = {r[1] for r in rows}
    latest = max(r[0] for r in rows)
    # F-02: a future-dated row would win MAX(date) and deactivate every other account. Rejected like a stale file,
    # for a fresh export and for a mirror alike (a mirror has no `today`, so the clock decides).
    ceiling = (today or date.today()) + timedelta(days=1)
    if date.fromisoformat(latest) > ceiling:
        return _reject(conn, now, source, f"future-dated export: latest date {latest} is later than tomorrow ({ceiling})")
    if today is not None:  # the guards of a fresh export; a mirror of rows the plan already accepted skips them
        if date.fromisoformat(latest) < today - timedelta(days=1):
            return _reject(conn, now, source, f"stale export: latest date {latest} is older than yesterday ({today - timedelta(days=1)})")
        prev = conn.execute("SELECT accounts FROM import_runs WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
        if prev and prev["accounts"] and len(keys) < prev["accounts"] * (1 - MAX_ACCOUNT_DROP):
            return _reject(conn, now, source, f"account count fell from {prev['accounts']} to {len(keys)} (more than {int(MAX_ACCOUNT_DROP * 100)}% drop)")

    # Display name = the name on each key's latest row.
    names: dict[str, tuple[str, str]] = {}
    for d, key, name, _ in rows:
        if key not in names or d >= names[key][0]:
            names[key] = (d, name)
    renames = _detect_renames(conn, rows)
    with conn:
        conn.executemany(
            "INSERT INTO balances (date, account_key, balance) VALUES (?,?,?) "
            "ON CONFLICT(date, account_key) DO UPDATE SET balance=excluded.balance",
            [(d, k, b) for d, k, _, b in rows],
        )
        for key, (_, name) in names.items():
            conn.execute(
                "INSERT INTO accounts (account_key, display_name, first_seen, last_seen) VALUES (?,?,?,?) "
                "ON CONFLICT(account_key) DO UPDATE SET display_name=excluded.display_name",
                (key, name, latest, latest),
            )
        for old, new in renames:
            _move_account(conn, old, new)
        if mirror:
            for (old,) in conn.execute("SELECT account_key FROM accounts").fetchall():
                if old not in keys:
                    conn.execute("DELETE FROM balances WHERE account_key=?", (old,))
                    conn.execute("DELETE FROM account_prefs WHERE account_key=?", (old,))
                    conn.execute("DELETE FROM accounts WHERE account_key=?", (old,))
        # first/last seen and active come from the stored history, not just this file.
        conn.execute(
            "UPDATE accounts SET "
            "first_seen=(SELECT MIN(date) FROM balances b WHERE b.account_key=accounts.account_key), "
            "last_seen=(SELECT MAX(date) FROM balances b WHERE b.account_key=accounts.account_key)"
        )
        overall = conn.execute("SELECT MAX(date) FROM balances").fetchone()[0]
        conn.execute("UPDATE accounts SET active = CASE WHEN last_seen = ? THEN 1 ELSE 0 END", (overall,))
    _record(conn, now, str(source), "ok", rows=len(rows), accounts=len(keys), latest=latest)
    return {"success": True, "status": "ok", "rows": len(rows), "accounts": len(keys), "latest_date": latest}


def freshness(db_path: str | Path) -> dict[str, Any]:
    """Latest import attempt and latest good import, for the staleness banner."""
    with closing(connect(db_path)) as conn:
        last = conn.execute("SELECT * FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
        ok = conn.execute("SELECT * FROM import_runs WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
        return {"last_run": dict(last) if last else None, "last_ok": dict(ok) if ok else None}
