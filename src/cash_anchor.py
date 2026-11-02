"""Anchored cash balance of a plan investment account (cash tracking Phase 4; integration task C.2).

When a broker file carries the broker's own running balance (Fidelity ``Cash Balance ($)``) the balance is *anchored*
(cash design 4.5, anchor 1): the import writes it to the account's ``CASH`` lot and records the old and new values in
the import's summary, so reverting the import restores the old lot. An unanchored import (no balance in the file) writes
nothing. This is the only importer writer of the ``CASH`` lot; no other lot of the account is touched, managed or not
(integration note 1.1). Sale confirmation never credits ``CASH`` (note 1.2).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

LARGE_CHANGE_MIN = 1000.0     # provisional: a change above this AND above LARGE_CHANGE_PCT of the old balance warns
LARGE_CHANGE_PCT = 0.25       # the owner sets the real threshold from the real files (phase 0 finding 5)


def _num(x: Any) -> float:
    try:
        return float(str(x).replace(",", "").replace("$", "").strip() or 0)
    except ValueError:
        return 0.0


def _fmt(x: float) -> str:
    return ("%.8f" % x).rstrip("0").rstrip(".") or "0"


def _is_cash_lot(r: Mapping[str, Any], account: str) -> bool:
    return (str(r.get("account") or "").strip().casefold() == account.casefold()
            and str(r.get("symbol") or "").strip().upper() == "CASH")


def anchor_of(rows: Iterable[Mapping[str, Any]]) -> tuple[float, str] | None:
    """``(balance, date)`` of the file's latest row that has a running balance; ``None`` when the file has none.
    Fidelity lists newest first, so on one day the lowest line number is the latest row."""
    best = None
    for r in rows:
        if r.get("cash_balance") is None:
            continue
        key = (str(r["run_date"]), -int(r.get("line") or 0))
        if best is None or key > best[0]:
            best = (key, float(r["cash_balance"]))
    return None if best is None else (round(best[1], 2), best[0][0])


def large_change(old: float, new: float) -> bool:
    d = abs(new - old)
    return d > LARGE_CHANGE_MIN and d > LARGE_CHANGE_PCT * abs(old)


def plan_write(rows: Iterable[Mapping[str, Any]], holdings: list[Mapping[str, Any]], account: str) -> dict[str, Any]:
    """What an import of ``rows`` would do to the ``CASH`` lot of ``account``; changes nothing."""
    anchor = anchor_of(rows)
    out: dict[str, Any] = {"anchored": anchor is not None, "write": False, "reason": "", "warning": ""}
    if anchor is None:
        out["reason"] = "no running balance in the file: the CASH lot is not changed"
        return out
    new, when = anchor
    lots = [l for l in holdings if _is_cash_lot(l, account)]
    out.update(new=_fmt(new), new_date=when)
    if len(lots) != 1:
        out["reason"] = ("the account has no CASH lot: add one to start tracking" if not lots
                         else "the account has several CASH lots: left alone")
        return out
    old, old_date = _num(lots[0].get("shares")), str(lots[0].get("purchase_date") or "")
    out.update(old=_fmt(old), old_date=old_date)
    if old_date and when < old_date:
        out["reason"] = f"the file ends {when}, before the CASH lot's {old_date}: not changed"
        return out
    out["write"] = True
    if large_change(old, new):
        out["warning"] = f"the cash balance changes by {new - old:+,.2f} (from {old:,.2f} to {new:,.2f}): check it"
    return out


def write(holdings_rows: list[dict[str, Any]], account: str, plan: Mapping[str, Any]) -> None:
    """Set the account's one CASH lot to the planned balance in ``holdings_rows`` (mutated in place)."""
    for r in holdings_rows:
        if _is_cash_lot(r, account):
            r["shares"], r["purchase_date"] = plan["new"], plan["new_date"]
            return


def restore(holdings_rows: list[dict[str, Any]], account: str, record: Mapping[str, Any]) -> bool:
    """Undo ``write`` while the lot still holds what it wrote; ``False`` when it was edited since (nothing changed)."""
    for r in holdings_rows:
        if _is_cash_lot(r, account):
            if abs(_num(r.get("shares")) - _num(record["new"])) > 1e-6 or str(r.get("purchase_date") or "") != record["new_date"]:
                return False
            r["shares"], r["purchase_date"] = record["old"], record["old_date"]
            return True
    return False
