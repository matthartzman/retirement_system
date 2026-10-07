"""Typed flat datasets of ``plan.db`` (schema v2, WP6.1 / P4.1): holdings lots, liabilities,
HSA schedule and target allocation.

Each dataset is one table that replaces one legacy CSV file. Columns keep the CSV column
names and are stored as text exactly as entered, so the build parses the same strings it
parsed from the file (no number formatting can move a result). Row order is the
``position`` column (0, 1, 2 ... in file order). The legacy CSV text form lives in
``csv_exchange.flat_csv`` (``dataset_csv_text`` / ``replace_dataset_from_csv_text``).
"""
from __future__ import annotations

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
        parts.append(f"CREATE TABLE {table} (\n    position INTEGER PRIMARY KEY,\n    {body}\n);")
    return "\n".join(parts)


SCHEMA_V2_DDL = _ddl()


class FlatDatasetRepository:
    """One flat dataset table of a ``PlanStore`` (implements ``DatasetRepository``)."""

    def __init__(self, store: Any, table: str) -> None:
        self._store = store
        self.table = table
        self.columns = _DATASETS[table]

    def rows(self) -> list[dict[str, str]]:
        """Rows in file order, keyed by the CSV column names."""
        with self._store._read() as con:
            cur = con.execute(f"SELECT {', '.join(self.columns)} FROM {self.table} ORDER BY position")
            return [dict(zip(self.columns, r)) for r in cur]

    def replace_all(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Atomically replace the dataset; return the number of rows written.

        Values must be text (``None`` is stored as an empty string); unknown column names
        raise ``ValidationError``. A failure leaves the old rows in place.
        """
        clean = [self._clean(r) for r in rows]
        marks = ", ".join("?" for _ in range(len(self.columns) + 1))
        with self._store._write() as con:
            con.execute(f"DELETE FROM {self.table}")
            con.executemany(
                f"INSERT INTO {self.table} (position, {', '.join(self.columns)}) VALUES ({marks})",
                [(i, *r) for i, r in enumerate(clean)],
            )
        return len(clean)

    def count(self) -> int:
        with self._store._read() as con:
            return int(con.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0])

    def _clean(self, row: Mapping[str, Any]) -> tuple[str, ...]:
        if not isinstance(row, Mapping):
            raise ValidationError(f"{self.table} row must be a mapping, got {type(row).__name__}")
        unknown = sorted(set(row) - set(self.columns))
        if unknown:
            raise ValidationError(f"unknown {self.table} column(s): {', '.join(unknown)}")
        out = []
        for c in self.columns:
            v = row.get(c, "")
            if v is None:
                v = ""
            if not isinstance(v, str):
                raise ValidationError(f"{self.table}.{c} must be str, got {type(v).__name__}")
            out.append(v)
        return tuple(out)
