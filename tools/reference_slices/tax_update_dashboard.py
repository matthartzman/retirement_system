"""Slice: tax-update dashboard -> table ``tax_update_status`` (WP3.1 demonstration slice).

Source ``reference_src/tax_update_dashboard.csv`` (a copy of the runtime file in
``reference_data/`` until WP3.5 moves it). Text fields are stored verbatim;
``blocking`` becomes 0/1 using the old loader's rule (TRUE/YES/1, case-insensitive);
``seq`` keeps file order. Getter: ``src/stores/ref_getters/tax_update_dashboard.py``.
"""
from __future__ import annotations

from pathlib import Path

from ._source import read_csv

SOURCES = ("tax_update_dashboard.csv",)
HEADER = ("constant", "category", "year", "source", "source_url", "last_reviewed",
          "review_frequency", "status", "blocking", "notes")


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    rows = []
    for seq, r in enumerate(read_csv(src / SOURCES[0], HEADER)):
        blocking = 1 if r["blocking"].strip().upper() in {"TRUE", "YES", "1"} else 0
        rows.append((seq, *(blocking if c == "blocking" else r[c] for c in HEADER)))
    return {"tax_update_status": (["seq", *HEADER], rows)}
