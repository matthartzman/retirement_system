"""The installment-sale gain inside each year's Note Receivable principal.

Each note item carries ``st_gain_per_principal`` / ``lt_gain_per_principal`` (parsed from its Form 8949 inputs,
``src/note_installment_tax.py``). The engine passes the principal each note paid this year; the short-term gain
is taxed as ordinary income (the Other Asset stacked path) and the long-term gain rides the LTCG line.

Design: documentation/archive/superpowers/plans/2026-11-06-note-installment-gain-tax-design-and-plan.md 4.2-4.3.
"""
from __future__ import annotations

from typing import Any, Iterable, NamedTuple


class NoteGains(NamedTuple):
    st: float  # short-term: ordinary income
    lt: float  # long-term: capital-gain rates

    @property
    def total(self) -> float:
        return self.st + self.lt


NO_NOTE_GAINS = NoteGains(0.0, 0.0)


def year_gains(principal_by_note: Iterable[tuple[dict[str, Any], float]]) -> NoteGains:
    """Sum each note's gain on the principal it paid this year."""
    st = lt = 0.0
    for item, principal in principal_by_note:
        p = max(0.0, float(principal or 0.0))
        st += p * float(item.get('st_gain_per_principal') or 0.0)
        lt += p * float(item.get('lt_gain_per_principal') or 0.0)
    return NoteGains(st, lt)
