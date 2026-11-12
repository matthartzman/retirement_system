"""Backlog intake rule (system review 2026-11-10, W1-07 / DOC-006).

A plan under documentation/future/ whose Status line says work is not built,
deferred, awaiting someone, or an owner task must have a BACKLOG.md row that
names the document, so approval gates and deferred work stay discoverable.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUTURE = ROOT / "documentation" / "future"
BACKLOG = ROOT / "documentation" / "reference" / "BACKLOG.md"

OPEN_WORK = re.compile(
    r"not built|deferred|\bawaits?\b|owner task|not approved|not yet run", re.IGNORECASE
)
STATUS_LINE = re.compile(r"\s*\**Status\**\s*:", re.IGNORECASE)


def _open_status_docs():
    for path in sorted(FUTURE.rglob("*.md")):
        head = path.read_text(encoding="utf-8").splitlines()[:20]
        for line in head:
            if STATUS_LINE.match(line) and OPEN_WORK.search(line):
                yield path
                break


def test_every_open_status_document_has_a_backlog_row():
    backlog = BACKLOG.read_text(encoding="utf-8")
    missing = [p.name for p in _open_status_docs() if p.name not in backlog]
    assert not missing, (
        "Status line says not built / deferred / awaits / owner task, but no BACKLOG.md "
        f"row names the document: {missing}. Add a row (see the inflow rule in BACKLOG.md)."
    )


def test_the_check_sees_the_known_open_documents():
    names = {p.name for p in _open_status_docs()}
    assert "2026-10-28-realized-sales-ledger-design-and-plan.md" in names
