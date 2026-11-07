"""Note Receivable installment-sale inputs (Form 8949 figures) and the gain ratios derived from them.

A note received for property sold is reported on the installment method: each principal payment is partly a
return of basis and partly gain, at a ratio fixed for the life of the note. The user copies one year's Form 8949
figures for the note -- short-term (Part I) and long-term (Part II) proceeds and basis -- and the plan taxes the
same fraction of every later principal payment. All four blank or $0 means no gain is modeled (the behaviour
before 2026-11).

Design: documentation/future/superpowers/plans/2026-11-06-note-installment-gain-tax-design-and-plan.md 4.1-4.2.
"""
from __future__ import annotations

import re

FIELDS = ("st_proceeds", "st_basis", "lt_proceeds", "lt_basis")

_HELP = {
    "st_proceeds": "Short-term proceeds per payment: one year's Form 8949 Part I, column (d), for this note.",
    "st_basis": "Short-term basis per payment: Form 8949 Part I, column (e).",
    "lt_proceeds": "Long-term proceeds per payment: Form 8949 Part II, column (d).",
    "lt_basis": "Long-term basis per payment: Form 8949 Part II, column (e).",
}

_NOTE_SUB = re.compile(r"^Note\s+\d+$", re.I)


def added_field_rows(subsection: str) -> list[list[str]]:
    """The four plan rows (``[section, subsection, label, value, units, notes]``) for one note: written by the
    add endpoint for a new note and backfilled into older notes."""
    return [["Note Receivable", subsection, label, "$0", "USD", _HELP[label]] for label in FIELDS]


def backfill_rows(store) -> list[list[str]]:
    """``added_field_rows`` for every ``Note N`` in the plan (the backfill engine drops the keys it holds)."""
    subs: list[str] = []
    for r in store.rows("Note Receivable"):
        sub = str(r["subsection"] or "")
        if _NOTE_SUB.match(sub.strip()) and sub not in subs:
            subs.append(sub)
    return [row for sub in subs for row in added_field_rows(sub)]


def _gain_ratio(proceeds: float, basis: float) -> float:
    if proceeds <= 0:
        return 0.0
    return max(0.0, proceeds - basis) / proceeds


def gain_ratios(st_proceeds: float, st_basis: float, lt_proceeds: float, lt_basis: float) -> tuple[float, float]:
    """``(short-term gain, long-term gain)`` per dollar of principal received.

    The two proceeds split each payment between the short- and long-term lots; each lot's gain ratio is
    (proceeds - basis) / proceeds, never below zero."""
    st_p = max(0.0, float(st_proceeds or 0.0))
    lt_p = max(0.0, float(lt_proceeds or 0.0))
    total = st_p + lt_p
    if total <= 0:
        return 0.0, 0.0
    st = st_p / total * _gain_ratio(st_p, max(0.0, float(st_basis or 0.0)))
    lt = lt_p / total * _gain_ratio(lt_p, max(0.0, float(lt_basis or 0.0)))
    return st, lt
