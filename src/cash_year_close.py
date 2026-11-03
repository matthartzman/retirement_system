"""Cash-year close (year-end transition Phase 1): the owner closes a calendar year of the cash reconciliation by hand.

Nothing closes a year automatically. A close freezes, in ``plan_meta`` key ``cash.year_close.<YYYY>``, the reported side
(withdrawals by pair status per account), the plan side (the engine's per-account ``_account_withdrawals`` from a saved
run that projected that year) and a digest of the year's ledger rows, so a late broker file shows as "changed since close"
instead of being absorbed. The close feeds no tax number; the engine is untouched. ``store`` only needs ``get_meta`` /
``set_meta`` / ``delete_meta`` (a ``PlanStore``); ledgers are read through ``cash_view`` unless the caller passes them.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from . import cash_view
from .platform_runtime import today

KEY = "cash.year_close.%04d"


class CloseError(ValueError):
    """A close or reopen the rules do not allow; the message is shown to the owner."""


def _load(store: Any, year: int) -> dict[str, Any] | None:
    raw = store.get_meta(KEY % year)
    return json.loads(raw) if raw else None


def record(store: Any, year: int) -> dict[str, Any] | None:
    return _load(store, year)


def is_year_closed(store: Any, year: int) -> bool:
    return _load(store, year) is not None


def _ledgers(store: Any, ledgers: Mapping[str, list[Mapping[str, Any]]] | None) -> Mapping[str, list[Mapping[str, Any]]]:
    return ledgers if ledgers is not None else cash_view._ledgers(store, cash_view._accounts(store))


def ledger_digest(ledgers: Mapping[str, list[Mapping[str, Any]]], year: int) -> str:
    """SHA-256 of the year's rows. ``pair_id`` is left out: it is a counter that changes when other rows do."""
    rows = sorted((a, r["date"], r["class"], round(float(r["amount"]), 2), r["pair_status"], r.get("partner_account") or "",
                   bool(r["counts"]), bool(r["in_kind"]))
                  for a, led in ledgers.items() for r in led if r["date"][:4] == f"{year:04d}")
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def _reported(ledgers: Mapping[str, list[Mapping[str, Any]]], year: int) -> dict[str, dict[str, float]]:
    return {a: {**cash_view.withdrawals_by_status(list(led), year), "excess_return": cash_view.excess_return(list(led), year)["amount"]}
            for a, led in sorted(ledgers.items())}


def pick_snapshot(snapshots: Sequence[Mapping[str, Any]], year: int) -> Mapping[str, Any] | None:
    """The newest snapshot (list is newest first) whose FIRST projection row is ``year``, else ``None``."""
    return next((s for s in snapshots if cash_view.plan_year_withdrawals(s, year) is not None), None)


def _straddles(ledgers: Mapping[str, list[Mapping[str, Any]]], year: int) -> list[dict[str, Any]]:
    return [s for s in cash_view.year_straddles(ledgers) if min(s["out_date"], s["in_date"])[:4] == f"{year:04d}"]


def service(input_dir: Any, year: int, action: str | None = None, *, note: str = "", straddles_seen: bool = False) -> dict[str, Any]:
    """Route body: status of ``year`` (no ``action``), or ``close`` / ``reopen`` it. Raises ``CloseError`` when not allowed."""
    from pathlib import Path
    from . import active_plan
    from .local_store import list_result_snapshots
    from .workspace_context import active_plan_id
    root = Path(input_dir).parent
    snaps = list_result_snapshots(plan_id=active_plan_id(root=root))
    with active_plan.workspace_store(root, write=action is not None) as store:
        if action == "close":
            close_year(store, year, note, snapshots=snaps, straddles_seen=straddles_seen)
        elif action == "reopen":
            reopen_year(store, year)
        elif action is not None:
            raise CloseError("action must be close or reopen")
        ledgers = _ledgers(store, None)
        return close_summary(store, year, ledgers) or close_status(store, year, ledgers=ledgers, snapshots=snaps)


def close_status(store: Any, year: int, *, ledgers: Mapping[str, list[Mapping[str, Any]]] | None = None,
                 snapshots: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    ledgers = _ledgers(store, ledgers)
    blockers = []
    if today() < today().replace(year=year + 1, month=1, day=1):
        blockers.append(f"{year} has not ended yet; a year can be closed from 1 January {year + 1}.")
    unmatched = sum(1 for led in ledgers.values() for r in led if r["pair_status"] == "unmatched" and r["date"][:4] == f"{year:04d}")
    if unmatched:
        blockers.append(f"{unmatched} unmatched cash row(s) dated {year} must be resolved first.")
    snap = pick_snapshot(snapshots, year)
    return {"year": year, "closed": is_year_closed(store, year), "allowed": not blockers, "blockers": blockers,
            "straddles": _straddles(ledgers, year),
            "snapshot": {"built_at": snap["created_at"]} if snap else None}


def close_year(store: Any, year: int, note: str = "", *, ledgers: Mapping[str, list[Mapping[str, Any]]] | None = None,
               snapshots: Sequence[Mapping[str, Any]] = (), straddles_seen: bool = False) -> dict[str, Any]:
    ledgers = _ledgers(store, ledgers)
    if is_year_closed(store, year):
        raise CloseError(f"{year} is already closed.")
    st = close_status(store, year, ledgers=ledgers, snapshots=snapshots)
    if not st["allowed"]:
        raise CloseError(" ".join(st["blockers"]))
    if st["straddles"] and not straddles_seen:
        raise CloseError(f"{len(st['straddles'])} transfer(s) straddle the year-end; confirm you have seen them before closing.")
    snap = pick_snapshot(snapshots, year)
    plan = ({"source": "snapshot", "built_at": snap["created_at"], "by_account": cash_view.plan_year_withdrawals(snap, year)}
            if snap else {"source": "none", "built_at": None, "by_account": {}})
    if snap and snap.get("plan_id"):
        plan["plan_id"] = snap["plan_id"]
    rec = {"year": year, "closed_at": f"{today().isoformat()}T{datetime.now(timezone.utc):%H:%M:%S}Z", "note": note or "",
           "reported": _reported(ledgers, year), "plan": plan, "ledger_digest": ledger_digest(ledgers, year)}
    store.set_meta(KEY % year, json.dumps(rec, sort_keys=True))
    return rec


def reopen_year(store: Any, year: int) -> None:
    if not is_year_closed(store, year):
        raise CloseError(f"{year} is not closed.")
    store.delete_meta(KEY % year)


def frozen_snapshot(rec: Mapping[str, Any]) -> dict[str, Any] | None:
    """The closed year's plan figure shaped like a saved run, so ``cash_view.comparison`` reads it unchanged."""
    plan = rec["plan"]
    if plan["source"] != "snapshot":
        return None
    return {"created_at": plan["built_at"], "plan_id": plan.get("plan_id"),
            "result": {"projection_rows": [{"year": rec["year"], "_account_withdrawals": plan["by_account"]}]}}


def close_summary(store: Any, year: int, ledgers: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any] | None:
    """What the panel shows for a closed year: the frozen figures, the per-account difference, and whether the ledger has
    changed since the close (old and new external-withdrawal totals)."""
    rec = _load(store, year)
    if rec is None:
        return None
    plan = rec["plan"]["by_account"] if rec["plan"]["source"] == "snapshot" else None
    by_fold = {k.casefold(): v for k, v in (plan or {}).items()}
    diff = [{"account": a, "reported": v["external_withdrawal"],
             "plan": by_fold.get(a.casefold(), 0.0) if plan is not None else None,
             "difference": round(by_fold.get(a.casefold(), 0.0) - v["external_withdrawal"], 2) if plan is not None else None}
            for a, v in rec["reported"].items()]
    now = _reported(ledgers, year)
    return {"year": year, "closed": True, "closed_at": rec["closed_at"], "note": rec["note"], "plan_source": rec["plan"]["source"],
            "built_at": rec["plan"]["built_at"], "difference": diff,
            "changed": ledger_digest(ledgers, year) != rec["ledger_digest"],
            "closed_total": round(sum(v["external_withdrawal"] for v in rec["reported"].values()), 2),
            "current_total": round(sum(v["external_withdrawal"] for v in now.values()), 2)}
