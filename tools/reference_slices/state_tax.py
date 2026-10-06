"""Slice: state tax rules -> table ``state_tax`` (WP3.3).

Source ``reference_src/state_tax.csv``. Every cell is stored as the verbatim CSV
string (percent signs, blanks and ``#`` rows included) so the getters reproduce
both the raw rows the admin estate pickers read and the parsed overlay
``taxes.load_state_tax`` builds; ``seq`` keeps file order. Getters:
``src/stores/ref_getters/state_tax.py``.
"""
from __future__ import annotations

from pathlib import Path

from ._source import read_csv

SOURCES = ("state_tax.csv",)
HEADER = ("state", "rate", "type", "exempt_retirement", "exempt_ss", "prop_rate", "sales_rate", "estate",
          "estate_exempt", "retirement_exempt_over_65", "source", "estate_calc")


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    rows = [(seq, *(r[c] for c in HEADER)) for seq, r in enumerate(read_csv(src / SOURCES[0], HEADER))]
    return {"state_tax": (["seq", *HEADER], rows)}
