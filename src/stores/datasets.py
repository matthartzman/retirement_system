"""Typed flat datasets of ``plan.db`` (schema v2, WP6.1 / P4.1): holdings lots, liabilities,
HSA schedule and target allocation.

Each dataset is one table that replaces one legacy CSV file. Columns keep the CSV column
names and are stored as text exactly as entered, so the build parses the same strings it
parsed from the file (no number formatting can move a result). Row order is the
``position`` column (0, 1, 2 ... in file order). The legacy CSV text form lives in
``csv_exchange.flat_csv`` (``dataset_csv_text`` / ``replace_dataset_from_csv_text``).
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .errors import ValidationError

HOLDINGS_COLUMNS = ("account", "symbol", "purchase_date", "shares", "purchase_price", "lot_type", "note")
LIABILITIES_COLUMNS = (
    "liability_id", "type", "label", "balance", "interest_rate",
    "monthly_payment", "start_year", "payoff_year", "notes",
)
HSA_SCHEDULE_COLUMNS = ("year", "optimizer_amount", "override_amount", "locked", "note")
TARGET_ALLOCATION_COLUMNS = ("asset_class", "target_pct")

_DATASETS: dict[str, tuple[str, ...]] = {
    "holdings_lots": HOLDINGS_COLUMNS,
    "liabilities": LIABILITIES_COLUMNS,
    "hsa_schedule": HSA_SCHEDULE_COLUMNS,
    "target_allocation": TARGET_ALLOCATION_COLUMNS,
}


def _ddl() -> str:
    parts = []
    for table, cols in _DATASETS.items():
        body = ",\n    ".join(f"{c} TEXT NOT NULL DEFAULT ''" for c in cols)
        parts.append(
            f"CREATE TABLE {table} (\n    position INTEGER PRIMARY KEY,\n    {body},\n"
            "    extra TEXT NOT NULL DEFAULT '{}'\n);"
        )
    return "\n".join(parts)


SCHEMA_V2_DDL = _ddl()


class FlatDatasetRepository:
    """One flat dataset table of a ``PlanStore`` (implements ``DatasetRepository``).

    A legacy file can carry columns beyond the known ones (``market_value``, ``asset_class``
    ... in a holdings file); they are kept per row as JSON in ``extra`` and come back from
    ``rows()`` as ordinary keys (``extra_columns()`` lists their names).
    """

    def __init__(self, store: Any, table: str) -> None:
        self._store = store
        self.table = table
        self.columns = _DATASETS[table]

    def rows(self) -> list[dict[str, str]]:
        """Rows in file order, keyed by the CSV column names (known columns first, then any
        extra columns the file carried)."""
        with self._store._read() as con:
            cur = con.execute(f"SELECT {', '.join(self.columns)}, extra FROM {self.table} ORDER BY position")
            out = []
            for r in cur:
                row = dict(zip(self.columns, r[:-1]))
                for k, v in json.loads(r[-1]).items():
                    row.setdefault(k, v)
                out.append(row)
            return out

    def extra_columns(self) -> list[str]:
        """Names of the extra (unknown) columns used by any row, sorted."""
        with self._store._read() as con:
            names: set[str] = set()
            for (blob,) in con.execute(f"SELECT extra FROM {self.table}"):
                names.update(json.loads(blob))
        return sorted(names)

    def replace_all(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Atomically replace the dataset; return the number of rows written.

        Values must be text (``None`` is stored as an empty string); columns other than the
        known ones are kept as extra columns. A failure leaves the old rows in place.
        """
        clean = [self._clean(r) for r in rows]
        marks = ", ".join("?" for _ in range(len(self.columns) + 2))
        with self._store._write() as con:
            con.execute(f"DELETE FROM {self.table}")
            con.executemany(
                f"INSERT INTO {self.table} (position, {', '.join(self.columns)}, extra) VALUES ({marks})",
                [(i, *vals, json.dumps(extra, ensure_ascii=False, sort_keys=True)) for i, (vals, extra) in enumerate(clean)],
            )
        return len(clean)

    def count(self) -> int:
        with self._store._read() as con:
            return int(con.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0])

    def _clean(self, row: Mapping[str, Any]) -> tuple[tuple[str, ...], dict[str, str]]:
        if not isinstance(row, Mapping):
            raise ValidationError(f"{self.table} row must be a mapping, got {type(row).__name__}")
        known: list[str] = []
        extra: dict[str, str] = {}
        for k, v in row.items():
            if v is None:
                v = ""
            if not isinstance(k, str) or not k:
                raise ValidationError(f"{self.table} column names must be non-empty text")
            if not isinstance(v, str):
                raise ValidationError(f"{self.table}.{k} must be str, got {type(v).__name__}")
            if k not in self.columns:
                extra[k] = v
        for c in self.columns:
            known.append(row.get(c) or "")
        return tuple(known), extra
