"""Year-end page (year-end transition Phase 2): an ordered checklist for moving the app from one calendar year to the next.

Each step's state is derived from the data (a step is done because the thing is true, not because a box was ticked); only
``personal_numbers`` has nothing to derive and stores a confirmation in ``plan_meta`` (``year_end.<YYYY>.<step>``). The page
reads and links to existing screens, runs nothing, and feeds no tax number. ``build`` is pure; ``service`` gathers the inputs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import cash_view, cash_year_close
from .platform_runtime import today

CONFIRMABLE = ("personal_numbers",)
_EPS = 0.005


def default_year() -> int:
    """The year to close: the one in progress from July, else the one that just ended."""
    t = today()
    return t.year if t.month >= 7 else t.year - 1


def in_season() -> bool:
    """Mid-December through January, when the page is announced on Plan Status."""
    t = today()
    return (t.month == 12 and t.day >= 15) or t.month == 1


def _key(year: int, step: str) -> str:
    return f"year_end.{year:04d}.{step}"


def is_confirmed(store: Any, year: int, step: str) -> bool:
    return store.get_meta(_key(year, step)) is not None


def set_confirmation(store: Any, year: int, step: str, confirmed: bool) -> None:
    if step not in CONFIRMABLE:
        raise ValueError(f"{step} is derived from the data and cannot be confirmed by hand")
    if confirmed:
        store.set_meta(_key(year, step), json.dumps({"confirmed": True, "at": today().isoformat()}))
    else:
        store.delete_meta(_key(year, step))


def _step(sid: str, title: str, link: str, state: str, detail: str) -> dict[str, str]:
    return {"id": sid, "title": title, "link": link, "state": state, "detail": detail}


def _growth_roles() -> frozenset[str]:
    from . import ytd_tracking
    return ytd_tracking.GROWTH_ROLES


def _year_of(value: Any) -> int:
    d = str(value or "")
    return int(d[:4]) if d[:4].isdigit() else 0


def build(year: int, *, store: Any, ledgers: Mapping[str, list[Mapping[str, Any]]], snapshots: Sequence[Mapping[str, Any]],
          imports: Sequence[Mapping[str, Any]], setup_rows: Sequence[Mapping[str, Any]],
          cash_differences: Sequence[tuple[str, float | None]], reference_stale: int) -> dict[str, Any]:
    """The checklist for closing ``year``. Inputs are plain data so the whole thing is testable without a plan file."""
    closed = cash_year_close.is_year_closed(store, year)
    st = cash_year_close.close_status(store, year, ledgers=ledgers, snapshots=snapshots)
    out = []

    snap = cash_year_close.pick_snapshot(snapshots, year)
    out.append(_step(
        "capture_plan_year", f"Capture the plan's {year}", "reports_and_review", "done" if snap or closed else "open",
        f"A saved plan run built {snap['created_at']} projects {year}." if snap else
        f"No saved plan run projects {year}. Build a report in December so the close has a plan figure; without one it closes with no plan figure."))

    latest: dict[str, str] = {}
    for i in imports:
        latest[i["account"]] = max(latest.get(i["account"], ""), str(i.get("date_to") or ""))
    behind = sorted(a for a, d in latest.items() if d < f"{year + 1:04d}-01-01")
    out.append(_step(
        "final_broker_files", "Import final broker files", "sales_ledger", "na" if not latest else "open" if behind else "done",
        "No broker imports yet." if not latest else
        f"No file dated after 31 Dec {year} for: {', '.join(behind)}." if behind else f"Every account has a file dated after 31 Dec {year}."))

    unmatched = sum(1 for led in ledgers.values() for r in led if r["pair_status"] == "unmatched" and r["date"][:4] == f"{year:04d}")
    strad = len(st["straddles"])
    out.append(_step(
        "resolve_cash_rows", "Resolve cash rows", "sales_ledger", "done" if not unmatched else "open",
        (f"{unmatched} unmatched cash row(s) dated {year}." if unmatched else f"No unmatched cash rows dated {year}.")
        + (f" {strad} transfer(s) straddle the year-end (listed, no action needed)." if strad else "")))

    off = [(a, d) for a, d in cash_differences if d is not None and abs(d) >= _EPS]
    out.append(_step(
        "confirm_year_end_cash", "Confirm year-end CASH balances", "sales_ledger",
        "na" if not cash_differences else "open" if off else "done",
        "No accounts with cash tracking." if not cash_differences else
        "Difference against the CASH lot: " + ", ".join(f"{a} {d:+,.2f}" for a, d in off) + "." if off else "Every anchored account matches its CASH lot."))

    out.append(_step("close_cash_year", f"Close the {year} cash year", "sales_ledger", "done" if closed else "open",
                     f"{year} is closed." if closed else " ".join(st["blockers"]) or f"Ready to close {year}."))

    growth = [r for r in setup_rows if str(r.get("Role") or "").strip() in _growth_roles()]
    stale = sorted(str(r.get("Account") or "") for r in growth if _year_of(r.get("Prior Year End Date")) < year)
    when = "" if today().year > year else f" (available from 1 January {year + 1})"
    out.append(_step(
        "start_tracking", f"Start {year + 1} tracking", "actual_spending", "na" if not growth else "open" if stale else "done",
        "No growth-tracked accounts." if not growth else
        f"Prior Year End Balance is older than {year} for: {', '.join(stale)}. Use the Start tracking prompt on Accounts & Sources{when}." if stale
        else "Prior Year End Balances are rolled forward."))

    ok = is_confirmed(store, year, "personal_numbers")
    out.append(_step("personal_numbers", "Update personal numbers", "household_people", "done" if ok else "open",
                     "Confirmed." if ok else "Salary, contribution elections, benefit letters and COLAs. Confirm when you have reviewed them."))

    out.append(_step(
        "reference_data", "Reference data", "start", "open" if reference_stale else "done",
        f"{reference_stale} reference constant(s) are overdue for review (maintainer-level, informational)." if reference_stale
        else "No reference constants are overdue."))
    return {"year": year, "closed": closed, "in_season": in_season(), "steps": out}


def _reference_stale() -> int:
    try:
        from . import governance
        return sum(1 for r in governance.tax_law_dashboard() if r.get("blocking"))
    except Exception:
        return 0


def service(input_dir: Any, year: int | None = None, *, confirm: tuple[str, bool] | None = None) -> dict[str, Any]:
    """Route body: the checklist for ``year`` (default ``default_year()``), optionally after setting a confirmation."""
    from . import active_plan
    from .local_store import list_result_snapshots
    from .workspace_context import active_plan_id
    root = Path(input_dir).parent
    year = year or default_year()
    snaps = list_result_snapshots(plan_id=active_plan_id(root=root))
    with active_plan.workspace_store(root, write=confirm is not None) as store:
        if confirm:
            set_confirmation(store, year, *confirm)
        ledgers = cash_view._ledgers(store, cash_view._accounts(store))
        view = cash_view.build_view(store, year=year, snapshots=snaps)
        return build(year, store=store, ledgers=ledgers, snapshots=snaps,
                     imports=[i for i in store.broker.list_imports() if i["status"] == "applied"],
                     setup_rows=store.dataset("ytd_account_setup").rows(),
                     cash_differences=[(a["account"], a["difference"]) for a in view["accounts"]], reference_stale=_reference_stale())
