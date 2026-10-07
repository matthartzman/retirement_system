"""Mortality table and real-loss curve rows from ``reference.db`` (WP3.5).

Tables ``mortality`` and ``real_loss`` (built by ``tools/reference_slices/mortality_real_loss.py``).
"""
from __future__ import annotations

from ..ref_access import reference
from ..ref_data import RefData

LOSS_COLUMNS = ("curve_name", "holding_years", "real_loss_prob", "notes")


def mortality_qx_table(ref: RefData | None = None) -> dict[int, tuple[float, float]]:
    """``{age: (male_qx, female_qx)}`` in age order, as the old CSV loader built it."""
    ref = reference() if ref is None else ref
    return {int(r["age"]): (float(r["male_qx"]), float(r["female_qx"]))
            for r in ref.query('SELECT age, male_qx, female_qx FROM "mortality" ORDER BY rowid')}


def real_loss_rows(ref: RefData | None = None) -> list[dict[str, str]]:
    """Real-loss curve rows in file order, every value a ``str`` (old ``csv.DictReader`` shape)."""
    ref = reference() if ref is None else ref
    sel = ", ".join(f'"{c}"' for c in LOSS_COLUMNS)
    return [{c: r[c] for c in LOSS_COLUMNS} for r in ref.query(f'SELECT {sel} FROM "real_loss" ORDER BY seq')]
