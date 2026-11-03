"""Anchored cash balance of a plan investment account (cash tracking Phase 4; integration task C.2).

When a broker file carries the broker's own running balance (Fidelity ``Cash Balance ($)``) the balance is *anchored*
(cash design 4.5, anchor 1): the import writes it to the account's ``CASH`` lot and records the old and new values in
the import's summary, so reverting the import restores the old lot. An unanchored import (no balance in the file) writes
nothing. This is the only importer writer of the ``CASH`` lot; no other lot of the account is touched, managed or not
(integration note 1.1). Sale confirmation never credits ``CASH`` (note 1.2).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from .cash_ledger import _broker_row

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


def flow_anchor(rows: Iterable[Mapping[str, Any]], lot: Mapping[str, Any], new_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Anchor 2 (cash design 4.5): the confirmed ``CASH`` lot plus the net cash flows of the file dated after the lot.

    ``rows`` is the whole file (its range must reach back to the lot), ``new_rows`` the rows not imported before, so a
    re-imported row is never counted twice. The result is ``{"balance", "date", "flows"}`` or ``{"reason"}`` when the
    lot cannot be rolled forward: no lot date (never confirmed), a file that starts more than a day after the lot (days
    between would be missing), or a file with nothing newer than the lot. The new date is the file's last day, so a
    later overlapping file adds only rows dated after it."""
    rows = list(rows)
    lot_date = str(lot.get("purchase_date") or "")
    if not lot_date:
        return {"reason": "the CASH lot has no date: confirm its balance and date first, then imports roll it forward"}
    days = sorted({str(r["run_date"]) for r in rows if r.get("run_date")})
    if not days:
        return {"reason": "no dated rows in the file: the CASH lot is not changed"}
    first, last = days[0], days[-1]
    if last <= lot_date:
        return {"reason": f"the file ends {last}, not after the CASH lot's {lot_date}: not changed"}
    if date.fromisoformat(first) > date.fromisoformat(lot_date) + timedelta(days=1):
        return {"reason": f"the file starts {first}, after the CASH lot's {lot_date}: the days between are missing, not changed"}
    flows = 0.0
    for r in new_rows:
        if str(r.get("run_date") or "") <= lot_date:
            continue
        led = _broker_row(r)
        if led and led["counts"] and not led["in_kind"]:
            flows += led["amount"]
    return {"balance": round(_num(lot.get("shares")) + flows, 2), "date": last, "flows": round(flows, 2)}


def plan_write(rows: Iterable[Mapping[str, Any]], holdings: list[Mapping[str, Any]], account: str,
               new_rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """What an import of ``rows`` would do to the ``CASH`` lot of ``account``; changes nothing.
    ``new_rows`` (default all of ``rows``) are the rows not imported before; anchor 2 sums only those."""
    rows = list(rows)
    anchor = anchor_of(rows)
    out: dict[str, Any] = {"anchored": anchor is not None, "anchor": "broker balance" if anchor else "", "write": False,
                           "reason": "", "warning": ""}
    lots = [l for l in holdings if _is_cash_lot(l, account)]
    if anchor is None:
        if len(lots) != 1:
            out["reason"] = "no running balance in the file: the CASH lot is not changed"
            return out
        fa = flow_anchor(rows, lots[0], rows if new_rows is None else new_rows)
        if "reason" in fa:
            out["reason"] = "no running balance in the file; " + fa["reason"]
            return out
        out.update(anchored=True, anchor="confirmed CASH lot plus flows", flows=_fmt(fa["flows"]))
        anchor = (fa["balance"], fa["date"])
    new, when = anchor
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
