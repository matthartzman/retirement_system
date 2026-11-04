"""Owner marks: "this outgoing cash row was a rollover" (cash tracking, owner decision 2026-11-04).

A rollover out of a plan account to another custodian is not a taxable withdrawal, but the ledger cannot tell it from one:
the other side is outside the plan, so the row pairs with nothing and reads ``external_withdrawal``. The owner marks it, and
the row becomes ``external_rollover``: still listed in the ledger, left out of the withdrawal totals (``cash_view``), so the
floor feed and the year-end comparison never see it.

A mark is a key ``account|date|amount`` kept in one ``plan_meta`` value, so it survives re-imports of the same rows. It only
applies to a row that would otherwise be an ``external_withdrawal`` or ``unmatched`` cash outflow; it never overrides a pair.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

KEY = "cash.rollover_marks"
STATUS = "external_rollover"
_MARKABLE = frozenset({"external_withdrawal", "unmatched"})


class MarkError(ValueError):
    """A mark the rules do not allow; the message is shown to the owner."""


def mark_key(account: str, date: str, amount: float) -> str:
    return f"{account.casefold()}|{str(date)[:10]}|{abs(round(float(amount), 2)):.2f}"


def load(store: Any) -> set[str]:
    raw = store.get_meta(KEY)
    if not raw:
        return set()
    try:
        return {str(k) for k in json.loads(raw)}
    except (TypeError, ValueError):
        return set()


def _save(store: Any, keys: set[str]) -> None:
    if keys:
        store.set_meta(KEY, json.dumps(sorted(keys)))
    else:
        store.delete_meta(KEY)


def _markable(r: Mapping[str, Any]) -> bool:
    return r["pair_status"] in _MARKABLE and r["class"] in ("distribution", "transfer_out") and not r["in_kind"] and r["amount"] < 0


def apply(store: Any, ledgers: Mapping[str, list[dict[str, Any]]]) -> None:
    """Set ``external_rollover`` on the marked rows of already-paired ledgers (rows are copies, changed in place)."""
    keys = load(store)
    if not keys:
        return
    for account, rows in ledgers.items():
        for r in rows:
            if _markable(r) and mark_key(account, r["date"], r["amount"]) in keys:
                r["pair_status"] = STATUS


def set_mark(store: Any, account: str, date: str, amount: float, marked: bool, *, ledgers: Mapping[str, list[Mapping[str, Any]]]) -> None:
    """Mark or unmark one row. ``ledgers`` must be the UNMARKED, paired ledgers so the row can be checked."""
    key = mark_key(account, date, amount)
    keys = load(store)
    if not marked:
        keys.discard(key)
        _save(store, keys)
        return
    rows = [r for r in ledgers.get(account, []) if r["date"][:10] == str(date)[:10] and abs(round(float(r["amount"]), 2)) == abs(round(float(amount), 2))]
    if not rows:
        raise MarkError(f"{account} has no cash row on {date} for {abs(float(amount)):.2f}.")
    if not any(_markable(r) for r in rows):
        raise MarkError("Only an outgoing cash row that is a withdrawal or unmatched can be marked as a rollover; this one is paired or is not an outflow.")
    keys.add(key)
    _save(store, keys)


def service(input_dir: Any, account: str, date: str, amount: float, marked: bool) -> dict[str, Any]:
    """Route body: set or clear one mark. Raises ``MarkError`` when not allowed."""
    from pathlib import Path
    from . import active_plan, cash_view
    with active_plan.workspace_store(Path(input_dir).parent, write=True) as store:
        accounts = cash_view._accounts(store)
        if account not in accounts:
            raise MarkError(f"{account} has no broker import.")
        ledgers = cash_view._ledgers(store, accounts, marks=False)
        set_mark(store, account, date, amount, marked, ledgers=ledgers)
        return {"account": account, "date": str(date)[:10], "amount": round(float(amount), 2), "marked": marked}
