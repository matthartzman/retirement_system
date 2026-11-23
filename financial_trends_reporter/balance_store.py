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
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_FILENAME = "monarch_balances.sqlite3"
EXPECTED_HEADER = ["date", "account_key", "account", "balance"]
MAX_ACCOUNT_DROP = 0.20  # reject a file with >20% fewer accounts than the last good import
SNAPSHOT_DIR = "snapshots"  # beside the database; F-03: a copy is taken before any import that can delete history
SNAPSHOTS_KEPT = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS balances (
    date TEXT NOT NULL,
    account_key TEXT NOT NULL,
    balance REAL NOT NULL,
    balance_cents INTEGER,
    PRIMARY KEY (date, account_key)
);
CREATE TABLE IF NOT EXISTS pending_renames (
    old_key TEXT NOT NULL,
    new_key TEXT NOT NULL,
    matched INTEGER NOT NULL,
    total INTEGER NOT NULL,
    detected_at TEXT NOT NULL,
    PRIMARY KEY (old_key, new_key)
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
    _migrate_cents(conn)
    return conn


def to_cents(balance: float) -> int | None:
    """``balance`` as whole cents when it is exactly a cent amount (to within float noise), else None.

    ``None`` means "keep the REAL value as it is": a value with sub-cent detail is never rounded away."""
    scaled = balance * 100.0
    cents = round(scaled)
    return int(cents) if abs(scaled - cents) < 1e-6 and abs(cents) < 2 ** 62 else None


def _migrate_cents(conn: sqlite3.Connection) -> None:
    """F-03: money is stored as integer cents next to the original REAL. Existing rows get their cents filled in
    only where the REAL is exactly a cent amount, and ``balance`` itself is never rewritten, so every existing value
    reads back bit-for-bit unchanged. Readers still use ``balance``; new writes keep the two in step."""
    if "balance_cents" not in {r["name"] for r in conn.execute("PRAGMA table_info(balances)")}:
        conn.execute("ALTER TABLE balances ADD COLUMN balance_cents INTEGER")
    pending = conn.execute("SELECT date, account_key, balance FROM balances WHERE balance_cents IS NULL").fetchall()
    if pending:
        conn.executemany("UPDATE balances SET balance_cents=? WHERE date=? AND account_key=?",
                         [(c, r["date"], r["account_key"]) for r in pending if (c := to_cents(r["balance"])) is not None])
        conn.commit()


def snapshot_db(conn: sqlite3.Connection, *, keep: int = SNAPSHOTS_KEPT, now: datetime | None = None) -> Path | None:
    """Copy the whole database with SQLite's backup API (consistent while open) into ``snapshots/`` beside it, newest
    ``keep`` kept. Returns the copy's path, or None for an in-memory or empty database."""
    row = next((r for r in conn.execute("PRAGMA database_list") if r["name"] == "main"), None)
    if row is None or not row["file"] or not conn.execute("SELECT 1 FROM balances LIMIT 1").fetchone():
        return None
    folder = Path(row["file"]).parent / SNAPSHOT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%f")
    dest = folder / f"{Path(row['file']).stem}-{stamp}.sqlite3"
    out = sqlite3.connect(str(dest))
    try:
        conn.commit()
        conn.backup(out)
    finally:
        out.close()
    for old in sorted(folder.glob(f"{Path(row['file']).stem}-*.sqlite3"))[:-max(1, keep)]:
        old.unlink(missing_ok=True)
    return dest


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


def _detect_renames(conn: sqlite3.Connection, rows: list[tuple[str, str, str, float]]) -> list[tuple[str, str, int, int]]:
    """Old key -> new key for a Monarch rename. The export has no account id, so a rename arrives as a new
    key repeating a stored key's history (same dates and balances) while the old key is gone from the file.
    Mirrors ``MonarchRepo.migrate_renames`` in the app's plan store. Each move is ``(old, new, matched, total)``."""
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
    moves: list[tuple[str, str, int, int]] = []
    for old, old_hist in stored.items():
        best, best_hits = None, 0
        for new, new_hist in candidates.items():
            hits = [d for d, b in old_hist.items() if d in new_hist and abs(new_hist[d] - b) < 0.005]
            if any(abs(old_hist[d]) >= 0.005 for d in hits) and len(hits) > best_hits:
                best, best_hits = new, len(hits)
        if best is None or best_hits < min(3, len(old_hist)) or best_hits < 0.8 * len(old_hist):
            continue
        candidates.pop(best)
        moves.append((old, best, best_hits, len(old_hist)))
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
    detected = _detect_renames(conn, rows)
    # F-03: a rename merge deletes the old key's history. It is automatic only when the new key repeats EVERY one of the
    # old rows exactly (nothing is lost); a partial match waits for an explicit confirm_rename().
    renames = [(o, n) for o, n, hit, total in detected if hit == total]
    held = [(o, n, hit, total) for o, n, hit, total in detected if hit != total]
    mirror_drops = [r[0] for r in conn.execute("SELECT account_key FROM accounts") if mirror and r[0] not in keys
                    and r[0] not in {o for o, _ in renames}]
    snapshot = snapshot_db(conn, now=now) if (renames or mirror_drops) else None
    with conn:
        conn.executemany(
            "INSERT INTO balances (date, account_key, balance, balance_cents) VALUES (?,?,?,?) "
            "ON CONFLICT(date, account_key) DO UPDATE SET balance=excluded.balance, balance_cents=excluded.balance_cents",
            [(d, k, b, to_cents(b)) for d, k, _, b in rows],
        )
        for old, new, hit, total in held:
            conn.execute("INSERT OR REPLACE INTO pending_renames (old_key, new_key, matched, total, detected_at) VALUES (?,?,?,?,?)",
                         (old, new, hit, total, now.isoformat(timespec="seconds")))
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
        _recompute_accounts(conn)
    _record(conn, now, str(source), "ok", rows=len(rows), accounts=len(keys), latest=latest,
            detail=(f"{len(held)} rename(s) await confirmation" if held else None))
    result = {"success": True, "status": "ok", "rows": len(rows), "accounts": len(keys), "latest_date": latest}
    if held:
        result["pending_renames"] = [{"old": o, "new": n, "matched": h, "of": t} for o, n, h, t in held]
    if snapshot is not None:
        result["snapshot"] = str(snapshot)
    return result


def pending_renames(db_path: str | Path) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM pending_renames ORDER BY old_key, new_key")]


def confirm_rename(db_path: str | Path, old: str, new: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Apply one held rename: the old key's type, match and chart choices move to the new key and the old key's
    history is deleted. A snapshot is taken first. Raises LookupError when no such rename is pending."""
    with closing(connect(db_path)) as conn:
        if not conn.execute("SELECT 1 FROM pending_renames WHERE old_key=? AND new_key=?", (old, new)).fetchone():
            raise LookupError(f"no pending rename {old!r} -> {new!r}")
        snapshot = snapshot_db(conn, now=now)
        with conn:
            _move_account(conn, old, new)
            conn.execute("DELETE FROM pending_renames WHERE old_key=?", (old,))
            conn.execute("DELETE FROM pending_renames WHERE new_key=?", (new,))
            _recompute_accounts(conn)
        return {"confirmed": [old, new], "snapshot": str(snapshot) if snapshot else None}


def reject_rename(db_path: str | Path, old: str, new: str) -> None:
    """Keep both keys as separate accounts and stop asking."""
    with closing(connect(db_path)) as conn, conn:
        conn.execute("DELETE FROM pending_renames WHERE old_key=? AND new_key=?", (old, new))


def _recompute_accounts(conn: sqlite3.Connection) -> None:
    """first/last seen and active come from the stored history, not just the last file."""
    conn.execute(
        "UPDATE accounts SET "
        "first_seen=(SELECT MIN(date) FROM balances b WHERE b.account_key=accounts.account_key), "
        "last_seen=(SELECT MAX(date) FROM balances b WHERE b.account_key=accounts.account_key)"
    )
    overall = conn.execute("SELECT MAX(date) FROM balances").fetchone()[0]
    conn.execute("UPDATE accounts SET active = CASE WHEN last_seen = ? THEN 1 ELSE 0 END", (overall,))


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def purge_future_rows(db_path: str | Path, *, today: date | None = None, apply: bool = False,
                      now: datetime | None = None) -> dict[str, Any]:
    """Remove balance rows dated after tomorrow (left by an import from before the F-02 date bound; a 2099 row
    deactivates every other account). Dry run unless ``apply``; ``apply`` snapshots first, deletes the rows, drops any
    account left with no history, and recomputes first/last seen and active. Returns what was or would be removed."""
    ceiling = ((today or date.today()) + timedelta(days=1)).isoformat()
    with closing(connect(db_path)) as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT date, account_key, balance FROM balances WHERE date > ? ORDER BY date, account_key", (ceiling,))]
        out: dict[str, Any] = {"ceiling": ceiling, "rows": len(rows), "dates": sorted({r["date"] for r in rows}),
                               "accounts": sorted({r["account_key"] for r in rows}), "applied": False, "snapshot": None}
        if not apply or not rows:
            return out
        snap = snapshot_db(conn, now=now)
        with conn:
            conn.execute("DELETE FROM balances WHERE date > ?", (ceiling,))
            for (key,) in conn.execute("SELECT account_key FROM accounts WHERE account_key NOT IN "
                                       "(SELECT DISTINCT account_key FROM balances)").fetchall():
                conn.execute("DELETE FROM account_prefs WHERE account_key=?", (key,))
                conn.execute("DELETE FROM accounts WHERE account_key=?", (key,))
            _recompute_accounts(conn)
        _record(conn, now or datetime.now(timezone.utc), "purge_future_rows", "purged", rows=len(rows),
                detail=f"removed {len(rows)} row(s) dated after {ceiling}")
        out.update(applied=True, snapshot=str(snap) if snap else None)
        return out


def freshness(db_path: str | Path) -> dict[str, Any]:
    """Latest import attempt and latest good import, for the staleness banner."""
    with closing(connect(db_path)) as conn:
        last = conn.execute("SELECT * FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
        ok = conn.execute("SELECT * FROM import_runs WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
        return {"last_run": dict(last) if last else None, "last_ok": dict(ok) if ok else None}
