"""Slice: security master -> table ``security_master`` (WP3.6).

Source ``reference_src/security_master.csv``; every cell is the verbatim CSV string
(the readers' strip/upper normalization stays in their code); ``seq`` keeps file
order (a later duplicate symbol wins, as before). Getter:
``src/stores/ref_getters/security_master.py``.
"""
from __future__ import annotations

from pathlib import Path

from ._source import read_csv

SOURCES = ("security_master.csv",)
HEADER = ("symbol", "asset_class", "sleeve", "region", "style", "notes")


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    rows = [(seq, *(r[c] for c in HEADER)) for seq, r in enumerate(read_csv(src / SOURCES[0], HEADER))]
    return {"security_master": (["seq", *HEADER], rows)}
