"""Transaction log of a plan file (schema v20): ``TransactionsRepo``, reached as ``store.transactions``.

``transactions``       one row per purchase, reinvestment, sale, in-kind transfer or opening lot. A row that creates a
                       lot (``buy``, ``reinvest``, ``transfer_in``, ``opening``) is that lot's id (``txn_id``).
``transaction_lots``   the lots a ``sell`` or ``transfer_out`` consumed and how many shares of each.
Rows are never deleted: ``void`` flips ``status`` and edits are void-and-replace (``revision_ref``). Monarch is never a
source: Monarch sales stay in the sales queue. Design: ``2026-10-31-transaction-log-design-and-plan.md`` section 3.1.
"""
from __future__ import annotations

from typing import Any, Iterable

from .errors import NotFoundError, ValidationError
from .sales_repo import _in

TYPES = ("buy", "reinvest", "sell", "transfer_out", "transfer_in", "opening")
LOT_TYPES_CREATING = ("buy", "reinvest", "transfer_in", "opening")
SOURCES = ("broker", "manual", "backfill")
STATUSES = ("active", "voided")

SCHEMA_V20_DDL = f"""
CREATE TABLE transactions (
    txn_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date         TEXT NOT NULL,
    settle_date      TEXT,
    account          TEXT NOT NULL CHECK (account <> ''),
    type             TEXT NOT NULL CHECK (type IN ({_in(TYPES)})),
    symbol           TEXT NOT NULL CHECK (symbol <> ''),
    shares           REAL NOT NULL CHECK (shares > 0),
    price            REAL,
    amount           REAL,
    fees             REAL NOT NULL DEFAULT 0,
    lot_type         TEXT NOT NULL DEFAULT '',
    transfer_group   TEXT,
    lot_date         TEXT,
    origin_lot_txn_id INTEGER,
    source           TEXT NOT NULL CHECK (source IN ({_in(SOURCES)})),
    activity_id      INTEGER,
    candidate_id     INTEGER,
    sale_ids         TEXT NOT NULL DEFAULT '[]',
    note             TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ({_in(STATUSES)})),
    revision_ref     INTEGER,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX ix_transactions_account ON transactions (account, symbol, txn_date);
CREATE UNIQUE INDEX ux_transactions_activity ON transactions (activity_id) WHERE activity_id IS NOT NULL AND status = 'active';
CREATE TABLE transaction_lots (
    txn_id      INTEGER NOT NULL,
    lot_txn_id  INTEGER NOT NULL,
    shares      REAL NOT NULL CHECK (shares > 0),
    PRIMARY KEY (txn_id, lot_txn_id)
) WITHOUT ROWID;
CREATE INDEX ix_transaction_lots_lot ON transaction_lots (lot_txn_id);
"""

_FIELDS = ("txn_date", "settle_date", "account", "type", "symbol", "shares", "price", "amount", "fees", "lot_type",
           "transfer_group", "lot_date", "origin_lot_txn_id", "source", "activity_id", "candidate_id", "note",
           "revision_ref")


class TransactionsRepo:
    def __init__(self, store: Any) -> None:
        self._store = store

    def insert(self, **f: Any) -> int:
        unknown = set(f) - set(_FIELDS)
        if unknown:
            raise ValidationError(f"unknown transaction field: {', '.join(sorted(unknown))}")
        if f.get("type") not in TYPES:
            raise ValidationError(f"type must be one of {', '.join(TYPES)}")
        if f.get("source") not in SOURCES:
            raise ValidationError(f"source must be one of {', '.join(SOURCES)} (Monarch sales are not logged)")
        try:
            shares = float(f.get("shares"))
        except (TypeError, ValueError):
            shares = 0.0
        if shares <= 0:
            raise ValidationError("shares must be greater than zero")
        for k in ("txn_date", "account", "symbol"):
            if not str(f.get(k) or "").strip():
                raise ValidationError(f"{k} is required")
        row = {k: f.get(k) for k in _FIELDS}
        row.update(shares=shares, fees=float(f.get("fees") or 0.0), lot_type=f.get("lot_type") or "", note=f.get("note") or "")
        now = self._store._clock()
        with self._store._write() as con:
            cur = con.execute(
                f"INSERT INTO transactions ({', '.join(_FIELDS)}, created_at, updated_at) "
                f"VALUES ({', '.join('?' * len(_FIELDS))}, ?, ?)", [*(row[k] for k in _FIELDS), now, now])
            return int(cur.lastrowid)

    def get(self, txn_id: int) -> dict[str, Any]:
        with self._store._read() as con:
            r = con.execute("SELECT * FROM transactions WHERE txn_id = ?", (txn_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"no transaction {txn_id}")
        return dict(r)

    def list(self, *, account: str | None = None, symbol: str | None = None, year: int | None = None,
             types: Iterable[str] | None = None, include_voided: bool = False) -> list[dict[str, Any]]:
        where, args = [], []
        if not include_voided:
            where.append("status = 'active'")
        if account is not None:
            where.append("account = ?"); args.append(account)
        if symbol is not None:
            where.append("UPPER(symbol) = ?"); args.append(symbol.upper())
        if year is not None:
            where.append("txn_date >= ? AND txn_date < ?"); args += [f"{int(year):04d}-01-01", f"{int(year) + 1:04d}-01-01"]
        types = list(types or [])
        if types:
            where.append(f"type IN ({', '.join('?' * len(types))})"); args += types
        sql = "SELECT * FROM transactions" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY txn_date, txn_id"
        with self._store._read() as con:
            return [dict(r) for r in con.execute(sql, args)]

    def void(self, txn_id: int) -> None:
        with self._store._write() as con:
            cur = con.execute("UPDATE transactions SET status = 'voided', updated_at = ? WHERE txn_id = ?",
                              (self._store._clock(), txn_id))
            if cur.rowcount == 0:
                raise NotFoundError(f"no transaction {txn_id}")

    def add_disposal(self, txn_id: int, lot_txn_id: int, shares: float) -> None:
        if float(shares) <= 0:
            raise ValidationError("shares must be greater than zero")
        with self._store._write() as con:
            con.execute("INSERT INTO transaction_lots (txn_id, lot_txn_id, shares) VALUES (?,?,?)",
                        (txn_id, lot_txn_id, float(shares)))

    def disposals(self, txn_id: int) -> list[dict[str, Any]]:
        with self._store._read() as con:
            return [dict(r) for r in con.execute(
                "SELECT lot_txn_id, shares FROM transaction_lots WHERE txn_id = ? ORDER BY lot_txn_id", (txn_id,))]

    def all_disposals(self) -> list[dict[str, Any]]:
        with self._store._read() as con:
            return [dict(r) for r in con.execute("SELECT txn_id, lot_txn_id, shares FROM transaction_lots")]

    def repoint_disposals(self, old_lot_txn_id: int, new_lot_txn_id: int) -> None:
        """A revised lot-creating row gets a new id; the sales that consumed the old lot follow it."""
        with self._store._write() as con:
            con.execute("UPDATE transaction_lots SET lot_txn_id = ? WHERE lot_txn_id = ?", (new_lot_txn_id, old_lot_txn_id))

    def release(self, txn_id: int, why: str) -> None:
        """Void a row that mirrored a broker row that is gone (import reverted, sale undone): drop the activity link so
        the same activity can be logged again later, and say why in the note."""
        row = self.get(txn_id)
        note = (row["note"] + " " if row["note"] else "") + why
        with self._store._write() as con:
            con.execute("UPDATE transactions SET status = 'voided', activity_id = NULL, note = ?, updated_at = ? WHERE txn_id = ?",
                        (note, self._store._clock(), txn_id))
