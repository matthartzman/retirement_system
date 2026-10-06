"""Slice: mortality table + real-loss curves -> tables ``mortality`` and ``real_loss`` (WP3.5).

Sources ``reference_src/mortality_table.csv`` (age, male/female qx as typed numbers,
provenance text) and ``real_loss_probability.csv`` (verbatim strings: the loader's
percent parsing stays in ``real_loss_curves``). Getters:
``src/stores/ref_getters/mortality_real_loss.py``.
"""
from __future__ import annotations

from pathlib import Path

from ._source import read_csv

SOURCES = ("mortality_table.csv", "real_loss_probability.csv")
MORT_HEADER = ("age", "male_qx", "female_qx", "source", "notes")
LOSS_HEADER = ("curve_name", "holding_years", "real_loss_prob", "notes")


def build(src: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    mort = [(int(r["age"]), float(r["male_qx"]), float(r["female_qx"]), r["source"], r["notes"])
            for r in read_csv(src / SOURCES[0], MORT_HEADER)]
    loss = [(seq, *(r[c] for c in LOSS_HEADER)) for seq, r in enumerate(read_csv(src / SOURCES[1], LOSS_HEADER))]
    return {"mortality": (list(MORT_HEADER), mort), "real_loss": (["seq", *LOSS_HEADER], loss)}
