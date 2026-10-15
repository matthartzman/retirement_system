"""Monarch account balances and reconciliation of a plan file (schema v13; v14 adds the match policy): ``MonarchRepo``,
reached as ``store.monarch``.

Typed tables (not flat text datasets), so a plan revision does not copy the ~18,000 balance rows:

``monarch_balances``       one row per (date, account_key): Monarch's daily balance history, upserted
                           by every import (each Monarch export carries the full history). Liabilities
                           are negative, as exported.
``monarch_balance_imports`` one row per import attempt (accepted or rejected) for guards and freshness.
``monarch_account_map``    saved matches from a Monarch account to an app account (``kind`` + ``ref``).
``reconcile_log``          every value copied from Monarch into the app, with the old and new text so a
                           change can be undone.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from .errors import NotFoundError, ValidationError

SCHEMA_V13_DDL = """
CREATE TABLE monarch_balances (
    date        TEXT NOT NULL,
    account_key TEXT NOT NULL,
    account     TEXT NOT NULL,
    balance     REAL NOT NULL,
    PRIMARY KEY (date, account_key)
) WITHOUT ROWID;
CREATE INDEX ix_monarch_balances_account ON monarch_balances (account_key, date);
CREATE TABLE monarch_balance_imports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT NOT NULL,
    source_file TEXT NOT NULL DEFAULT '',
    rows        INTEGER NOT NULL DEFAULT 0,
    accounts    INTEGER NOT NULL DEFAULT 0,
    latest_date TEXT,
    status      TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE monarch_account_map (
    account_key TEXT NOT NULL PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind <> ''),
    ref         TEXT NOT NULL DEFAULT ''
);
CREATE TABLE reconcile_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    applied_at    TEXT NOT NULL,
    kind          TEXT NOT NULL,
    ref           TEXT NOT NULL,
    field         TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    old_value     TEXT NOT NULL,
    new_value     TEXT NOT NULL,
    monarch_date  TEXT NOT NULL DEFAULT '',
    undone_at     TEXT
);
"""


# v14: what the page does when a mapped account's number differs from the app's.
#   ask    show it in the inbox; the user chooses (the default for a new match)
#   auto   copy Monarch's number into the app at import (guarded; see reconcile)
#   app    the app is the source: report the difference, never write
#   ignore never compare (kept so the match is remembered)
POLICIES = ("ask", "auto", "app", "ignore")
DEFAULT_POLICY = "ask"
SCHEMA_V14_DDL = f"""
ALTER TABLE monarch_account_map ADD COLUMN policy TEXT NOT NULL DEFAULT '{DEFAULT_POLICY}'
    CHECK (policy IN ({", ".join(repr(p) for p in POLICIES)}));
UPDATE monarch_account_map SET policy = 'ignore' WHERE kind = 'ignore';
"""

# An account whose last row is within this many days of the newest stored date is treated as still live
# (a late sync), not closed: its last balance carries forward instead of dropping to 0.
CLOSED_GRACE_DAYS = 3


class MonarchRepo:
    """The Monarch tables of one open ``PlanStore`` (``store.monarch``). Cheap to create;
    writes join the store's enclosing ``transaction()`` like every other store write."""

    def __init__(self, store: Any) -> None:
        self._store = store

    # ------------------------------------------------------------------ balances
    def upsert_balances(self, rows: Iterable[tuple[str, str, str, float]]) -> int:
        """Insert or refresh ``(date, account_key, account, balance)`` rows; returns the count."""
        data = [(str(d), str(k), str(a), float(b)) for d, k, a, b in rows]
        with self._store._write() as con:
            con.executemany(
                "INSERT INTO monarch_balances (date, account_key, account, balance) VALUES (?,?,?,?) "
                "ON CONFLICT (date, account_key) DO UPDATE SET account = excluded.account, balance = excluded.balance",
                data,
            )
        return len(data)

    def count(self) -> int:
        with self._store._read() as con:
            return int(con.execute("SELECT COUNT(*) FROM monarch_balances").fetchone()[0])

    def latest_date(self) -> str | None:
        with self._store._read() as con:
            return con.execute("SELECT MAX(date) FROM monarch_balances").fetchone()[0]

    def dates(self, limit: int = 4000) -> list[str]:
        """Distinct stored dates, newest first (for the as-of picker)."""
        with self._store._read() as con:
            return [r[0] for r in con.execute("SELECT DISTINCT date FROM monarch_balances ORDER BY date DESC LIMIT ?", (limit,))]

    def accounts_as_of(self, as_of: str) -> list[dict[str, Any]]:
        """Each Monarch account that has a row on or before ``as_of``: its display name (the latest row's)
        and its balance on ``as_of``, carried forward from its last row on or before that date. An account
        whose last stored row is before ``as_of`` is ``closed`` and counts as 0, the same rule as the
        trends reporter's daily series."""
        with self._store._read() as con:
            newest = con.execute("SELECT MAX(date) FROM monarch_balances").fetchone()[0]
            if newest is None:
                return []
            live_from = (date.fromisoformat(newest) - timedelta(days=CLOSED_GRACE_DAYS)).isoformat()
            # One pass: each account's first/last date, its latest name, and its last row on or before as_of.
            rows = con.execute(
                "SELECT s.account_key, s.first, s.last, n.account, v.date, v.balance FROM "
                "(SELECT account_key, MIN(date) AS first, MAX(date) AS last FROM monarch_balances GROUP BY account_key) s "
                "JOIN monarch_balances n ON n.account_key = s.account_key AND n.date = s.last "
                "JOIN (SELECT b.account_key, b.date, b.balance FROM monarch_balances b JOIN "
                "      (SELECT account_key, MAX(date) AS d FROM monarch_balances WHERE date <= ? GROUP BY account_key) m "
                "      ON b.account_key = m.account_key AND b.date = m.d) v ON v.account_key = s.account_key",
                (as_of,)).fetchall()
            out = []
            for key, first, last, name, bal_date, balance in rows:
                # Closed: no row on or after as_of AND it stopped well before the newest stored date.
                closed = last < as_of and last < live_from
                out.append({
                    "account_key": key, "account": name, "balance": 0.0 if closed else float(balance),
                    "last_balance": float(balance),  # what a closed account held when it stopped
                    "balance_date": bal_date, "first_date": first, "last_date": last, "closed": closed,
                })
            return sorted(out, key=lambda r: r["account"].casefold())

    # ------------------------------------------------------------------ import audit
    def record_import(self, run_at: str, source_file: str, status: str, *, rows: int = 0, accounts: int = 0,
                      latest_date: str | None = None, detail: str = "") -> int:
        with self._store._write() as con:
            cur = con.execute(
                "INSERT INTO monarch_balance_imports (run_at, source_file, rows, accounts, latest_date, status, detail) "
                "VALUES (?,?,?,?,?,?,?)", (run_at, source_file, rows, accounts, latest_date, status, detail))
            return int(cur.lastrowid)

    def last_import(self, *, ok_only: bool = False) -> dict[str, Any] | None:
        sql = "SELECT * FROM monarch_balance_imports " + ("WHERE status = 'ok' " if ok_only else "") + "ORDER BY id DESC LIMIT 1"
        with self._store._read() as con:
            r = con.execute(sql).fetchone()
            return dict(r) if r else None

    # ------------------------------------------------------------------ account map
    def mapping(self) -> dict[str, dict[str, str]]:
        with self._store._read() as con:
            return {r["account_key"]: {"kind": r["kind"], "ref": r["ref"], "policy": r["policy"]}
                    for r in con.execute("SELECT * FROM monarch_account_map")}

    def set_mapping(self, account_key: str, kind: str, ref: str = "", policy: str | None = None) -> None:
        """Save a match. ``policy`` None keeps the account's current policy (``ask`` for a new match;
        an ``ignore`` kind is always policy ``ignore``)."""
        if not account_key or not kind:
            raise ValidationError("a mapping needs an account key and a kind")
        if policy is not None and policy not in POLICIES:
            raise ValidationError(f"unknown policy {policy!r}; one of {', '.join(POLICIES)}")
        if kind == "ignore":
            policy = "ignore"
        with self._store._write() as con:
            con.execute(
                "INSERT INTO monarch_account_map (account_key, kind, ref, policy) VALUES (?,?,?,?) "
                "ON CONFLICT (account_key) DO UPDATE SET kind = excluded.kind, ref = excluded.ref, "
                "policy = CASE WHEN ? IS NULL THEN monarch_account_map.policy ELSE excluded.policy END",
                (account_key, kind, ref, policy or DEFAULT_POLICY, policy))

    def set_policy(self, account_key: str, policy: str) -> None:
        if policy not in POLICIES:
            raise ValidationError(f"unknown policy {policy!r}; one of {', '.join(POLICIES)}")
        with self._store._write() as con:
            cur = con.execute("UPDATE monarch_account_map SET policy = ? WHERE account_key = ?", (policy, account_key))
            if cur.rowcount == 0:
                raise NotFoundError(f"no saved match for {account_key!r}")

    def clear_mapping(self, account_key: str) -> None:
        with self._store._write() as con:
            con.execute("DELETE FROM monarch_account_map WHERE account_key = ?", (account_key,))

    # ------------------------------------------------------------------ reconcile log
    def log_change(self, applied_at: str, kind: str, ref: str, field: str, label: str, old_value: str,
                   new_value: str, monarch_date: str) -> int:
        with self._store._write() as con:
            cur = con.execute(
                "INSERT INTO reconcile_log (applied_at, kind, ref, field, label, old_value, new_value, monarch_date) "
                "VALUES (?,?,?,?,?,?,?,?)", (applied_at, kind, ref, field, label, old_value, new_value, monarch_date))
            return int(cur.lastrowid)

    def log_entries(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._store._read() as con:
            return [dict(r) for r in con.execute("SELECT * FROM reconcile_log ORDER BY id DESC LIMIT ?", (limit,))]

    def log_entry(self, entry_id: int) -> dict[str, Any]:
        with self._store._read() as con:
            r = con.execute("SELECT * FROM reconcile_log WHERE id = ?", (entry_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"no reconcile change {entry_id}")
        return dict(r)

    def mark_undone(self, entry_id: int, undone_at: str) -> None:
        with self._store._write() as con:
            con.execute("UPDATE reconcile_log SET undone_at = ? WHERE id = ?", (undone_at, entry_id))
