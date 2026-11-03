"""Read-only view for the "Cash in investment accounts" panel (cash tracking Phase 5): nothing is stored.

Per account with a broker import: balance and its anchor (cash design 4.5), the account's ``CASH`` lot and the difference,
the last cash flow, unpaired transfers; cash income of the year grouped by the account's tax class (design 4.6); and one
account's ledger rows with their pairing status. Ledgers come from ``cash_ledger``, pairing from ``cash_pairing``.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping

from . import active_plan
from .platform_runtime import today
from .cash_ledger import account_ledger
from .cash_pairing import pair_transfers
from .sales_confirm import default_tax_class

_EPS = 0.005


def _num(x: Any) -> float:
    try:
        return float(str(x).replace(",", "") or 0)
    except ValueError:
        return 0.0


def _accounts(store: Any) -> list[str]:
    return sorted({i["account"] for i in store.broker.list_imports() if i["status"] == "applied"})


def _monarch_names(store: Any, account: str) -> set[str]:
    return {str(r.get("Account") or "").strip().lower() for r in store.dataset("ytd_account_setup").rows()
            if str(r.get("Mapped Investment Account") or "").strip().lower() == account.strip().lower()}


def _flow(r: Mapping[str, Any]) -> float:
    return 0.0 if (r["in_kind"] or not r["counts"]) else float(r["amount"])


def anchor(ledger: list[Mapping[str, Any]], lot: Mapping[str, Any] | None) -> dict[str, Any]:
    """``{type, balance, as_of}``: the file's latest running balance, else the confirmed CASH lot, else unanchored.
    Counted flows dated after the anchor (rows no broker file covers) are added. Within one day the first stored
    row is the latest (the files list newest first)."""
    dated = [r for r in ledger if r.get("cash_balance") is not None]
    if dated:
        last = max(r["date"] for r in dated)
        base = next(r["cash_balance"] for r in dated if r["date"] == last)
        kind, when = "broker balance", last
    elif lot is not None and str(lot.get("purchase_date") or ""):
        base, kind, when = _num(lot.get("shares")), "confirmed CASH lot", str(lot["purchase_date"])
    else:
        return {"type": "unanchored", "balance": None, "as_of": None}
    after = sum(_flow(r) for r in ledger if r["date"] > when)
    return {"type": kind, "balance": round(base + after, 2), "as_of": max([when] + [r["date"] for r in ledger if r["date"] > when])}


def withdrawals_by_status(ledger: list[Mapping[str, Any]], year: int) -> dict[str, float]:
    """REPORT-ONLY (cash plan section 10 item 3): cash that left the account in ``year`` by pair status. An ``internal`` pair is
    not a withdrawal, an ``external_withdrawal`` is one, ``unmatched`` is undecided. ``excess_return`` is excluded (see
    ``excess_return``). Nothing here reaches the engine's tax numbers."""
    out = {"external_withdrawal": 0.0, "internal": 0.0, "unmatched": 0.0}
    for r in ledger:
        if r["class"] in ("distribution", "transfer_out") and r["counts"] and not r["in_kind"] \
                and r["date"][:4] == f"{year:04d}" and r["pair_status"] in out:
            out[r["pair_status"]] = round(out[r["pair_status"]] - float(r["amount"]), 2)
    return out


def excess_return(ledger: list[Mapping[str, Any]], year: int) -> dict[str, Any]:
    """Returned excess contributions of ``year``: untaxed and not external spending (cash plan 9.5); the earnings on them
    are taxable and the user is flagged to enter them."""
    rows = [r for r in ledger if r["class"] == "excess_return" and r["date"][:4] == f"{year:04d}"]
    return {"count": len(rows), "amount": round(-sum(float(r["amount"]) for r in rows), 2)}


def is_year_closed(store: Any, year: int) -> bool:
    """True once the owner has closed ``year`` by hand (``cash_year_close``). Only a closed year gets a plan-minus-reported
    difference."""
    from . import cash_year_close
    return cash_year_close.is_year_closed(store, year)


def plan_year_withdrawals(snapshot: Mapping[str, Any] | None, year: int) -> dict[str, float] | None:
    """The engine's per-account ``_account_withdrawals`` for ``year`` from a saved result snapshot, else ``None``.
    The engine projects from plan_start (today's year, so it moves on 1 Jan): a snapshot counts only when its FIRST
    projection row is ``year``, otherwise there is no plan figure for that year."""
    rows = ((snapshot or {}).get("result") or {}).get("projection_rows") or []
    if not rows or str(rows[0].get("year")) != str(year):
        return None
    for r in rows:
        if str(r.get("year")) == str(year):
            return {str(k): round(_num(v), 2) for k, v in (r.get("_account_withdrawals") or {}).items()}
    return None


def comparison(ledgers: Mapping[str, list[Mapping[str, Any]]], year: int, snapshot: Mapping[str, Any] | None, *,
               closed: bool) -> dict[str, Any]:
    """REPORT-ONLY pace: year-to-date reported ``external_withdrawal`` beside the engine's full-year figure from the newest
    saved snapshot. ``difference`` (plan - reported) only for a closed year."""
    plan = plan_year_withdrawals(snapshot, year)
    by_fold = {k.casefold(): k for k in (plan or {})}
    used, rows = set(), []
    for a in sorted(ledgers):
        rep = withdrawals_by_status(list(ledgers[a]), year)["external_withdrawal"]
        key = by_fold.get(a.casefold())
        pl = plan[key] if plan is not None and key is not None else (0.0 if plan is not None else None)
        if key is not None:
            used.add(key)
        rows.append({"account": a, "reported_ytd": rep, "plan": pl,
                     "difference": round(pl - rep, 2) if closed and pl is not None else None})
    return {"year": year, "closed": closed, "accounts": rows,
            "snapshot": {"built_at": snapshot["created_at"]} if snapshot else None,
            "plan_unmapped": {k: v for k, v in (plan or {}).items() if k not in used and v},
            "note": ("No plan figure for %d: the newest saved plan run starts in another year. Run the plan." % year
                     if snapshot and plan is None else
                     "Plan figures come from the newest saved run of this plan and may be stale."
                     + ("" if (snapshot or {}).get("plan_id") else " That run carries no plan identifier, so it cannot be verified as the active plan's.")
                     + " The panel never runs the plan.")
            if snapshot else "No saved plan run for this plan yet; run the plan to see its figures."}


def past_years(ledgers: Mapping[str, list[Mapping[str, Any]]], year: int) -> list[dict[str, Any]]:
    """Reported withdrawals of earlier years by pair status (no engine column: the engine has no past-year rows)."""
    out = []
    for a in sorted(ledgers):
        for y in sorted({int(r["date"][:4]) for r in ledgers[a] if r["date"][:4].isdigit() and int(r["date"][:4]) < year}):
            out.append({"account": a, "year": y, **withdrawals_by_status(list(ledgers[a]), y)})
    return out


def year_straddles(ledgers: Mapping[str, list[Mapping[str, Any]]], days: int = 5) -> list[dict[str, Any]]:
    """Internal pairs whose outflow or inflow is within ``days`` of 31 Dec and whose partner falls in the other year.
    Listed only: every row still counts in the year of its own date."""
    byid: dict[Any, list[Mapping[str, Any]]] = {}
    for a in ledgers:
        for r in ledgers[a]:
            if r.get("pair_id") and r.get("pair_status") == "internal":
                byid.setdefault(r["pair_id"], []).append({**r, "account": a})
    out = []
    for pair in byid.values():
        outs = [r for r in pair if float(r["amount"]) < 0]
        ins = [r for r in pair if float(r["amount"]) > 0]
        if len(outs) != 1 or len(ins) != 1 or outs[0]["date"][:4] == ins[0]["date"][:4]:
            continue
        d1, d2 = date.fromisoformat(outs[0]["date"]), date.fromisoformat(ins[0]["date"])
        edge = date(min(d1, d2).year, 12, 31)
        if all(abs((d - edge).days) <= days for d in (d1, d2)):
            out.append({"out_account": outs[0]["account"], "out_date": outs[0]["date"], "in_account": ins[0]["account"],
                        "in_date": ins[0]["date"], "amount": round(-float(outs[0]["amount"]), 2)})
    return sorted(out, key=lambda x: (x["out_date"], x["out_account"]))


def _ledgers(store: Any, accounts: list[str]) -> dict[str, list[dict[str, Any]]]:
    return pair_transfers({a: account_ledger(store, a, _monarch_names(store, a)) for a in accounts})


def _cash_lot(store: Any, account: str) -> dict[str, Any] | None:
    lots = [l for l in store.dataset("holdings").rows()
            if str(l.get("account") or "").strip().casefold() == account.casefold()
            and str(l.get("symbol") or "").strip().upper() == "CASH"]
    return lots[0] if len(lots) == 1 else None


def _closes(store: Any, ledgers: Mapping[str, list[Mapping[str, Any]]], snapshots: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One entry per ended year with cash rows: its frozen close summary, else what blocks or allows closing it."""
    from . import cash_year_close as cyc
    ended = sorted({int(r["date"][:4]) for led in ledgers.values() for r in led if r["date"][:4].isdigit() and int(r["date"][:4]) < today().year})
    return [cyc.close_summary(store, y, ledgers) or cyc.close_status(store, y, ledgers=ledgers, snapshots=snapshots) for y in ended]


def build_view(store: Any, *, year: int | None = None, snapshot: Mapping[str, Any] | None = None,
               snapshots: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    from . import cash_year_close as cyc
    year = year or today().year
    snapshots = snapshots if snapshots is not None else ([snapshot] if snapshot else [])
    snapshot = snapshot or (snapshots[0] if snapshots else None)
    accounts = _accounts(store)
    ledgers = _ledgers(store, accounts)
    from . import cash_verified_accounts
    gate = cash_verified_accounts.eligibility(store, year, ledgers)
    rows, income = [], {}
    for a in accounts:
        led, lot = ledgers[a], _cash_lot(store, a)
        an = anchor(led, lot)
        lot_shares = _num(lot.get("shares")) if lot else None
        flows = [r for r in led if r["counts"] and not r["in_kind"]]
        rows.append({"account": a, "balance": an["balance"], "as_of": an["as_of"], "anchor": an["type"],
                     "cash_lot": lot_shares, "lot_date": (lot or {}).get("purchase_date") or "",
                     "difference": None if an["balance"] is None or lot_shares is None else round(an["balance"] - lot_shares, 2),
                     "last_flow": max((r["date"] for r in flows), default=None),
                     "tax_class": default_tax_class(store, a), "withdrawals": withdrawals_by_status(led, year),
                     "excess_return": excess_return(led, year), "floor_gate": gate[a],
                     "unmatched": sum(1 for r in led if r["pair_status"] == "unmatched"),
                     "review": sum(1 for r in led if r["needs_review"])})
        cls = default_tax_class(store, a)
        for r in led:
            if r["class"] == "income" and r["counts"] and r["date"][:4] == f"{year:04d}":
                income[cls] = round(income.get(cls, 0.0) + float(r["amount"]), 2)
    rec = cyc.record(store, year)
    return {"year": year, "accounts": rows, "income_by_tax_class": income,
            "comparison": comparison(ledgers, year, cyc.frozen_snapshot(rec) if rec else snapshot, closed=rec is not None),
            "past_years": past_years(ledgers, year), "straddles": year_straddles(ledgers),
            "closes": _closes(store, ledgers, snapshots)}


def ledger_view(store: Any, account: str) -> dict[str, Any]:
    accounts = _accounts(store)
    if account not in accounts:
        return {"account": account, "rows": []}
    out = [{k: r[k] for k in ("date", "class", "amount", "cash_balance", "pair_status", "partner_account", "source",
                              "description", "counts", "in_kind", "needs_review")} for r in _ledgers(store, accounts)[account]]
    return {"account": account, "rows": out}


def view(input_dir: str | Path, *, account: str | None = None, year: int | None = None) -> dict[str, Any]:
    with active_plan.workspace_store(Path(input_dir).parent) as store:
        if account:
            return ledger_view(store, account)
        from .local_store import list_result_snapshots
        from .workspace_context import active_plan_id
        return build_view(store, year=year, snapshots=list_result_snapshots(plan_id=active_plan_id(root=Path(input_dir).parent)))
