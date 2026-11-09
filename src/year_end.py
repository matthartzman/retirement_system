"""Year-end page (year-end transition Phase 2): an ordered checklist for moving the app from one calendar year to the next.

Each step's state is derived from the data (a step is done because the thing is true, not because a box was ticked); only
``personal_numbers`` and ``tie_1099b`` (``CONFIRMABLE``) store a confirmation in ``plan_meta`` (``year_end.<YYYY>.<step>``).
``personal_numbers`` has nothing to derive; a ``tie_1099b`` confirmation counts only while the untied count is unknown. The page
reads and links to existing screens, runs nothing, and feeds no tax number. ``build`` is pure; ``service`` gathers the inputs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import cash_view, cash_year_close
from .platform_runtime import today

log = logging.getLogger(__name__)
CONFIRMABLE = ("personal_numbers", "tie_1099b")
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


def _step(sid: str, title: str, link: str, state: str, detail: str, hash: str | None = None) -> dict[str, str]:
    out = {"id": sid, "title": title, "link": link, "state": state, "detail": detail}
    if hash:
        out["hash"] = hash   # deep link into the target page (the Sales Ledger's tab and section)
    return out


_WASH_DETAIL = {"clean": "No possible wash sales are flagged.", "flagged": "Possible wash sales are flagged — review them.",
                "stale": "The check has not run since the ledger changed.", "never": "The check has never run."}
_COULD_NOT_CHECK = "Could not check — open the Sales Ledger page to see it."


def _tax_filing_steps(year: int, tf: Mapping[str, Any] | None, tied_confirmed: bool = False) -> list[dict[str, str]]:
    """The Sales Ledger's tax-filing steps; all ``na`` when ``tf`` (see ``service``) is None. ``tied_confirmed`` is the
    stored attestation for ``tie_1099b``; it counts only while the tie count is unknown (a known untied count wins)."""
    def step(sid: str, title: str, hash_: str, done: bool, detail: str) -> dict[str, str]:
        return _step(sid, title, "sales_ledger", "na" if tf is None else "done" if done else "open",
                     "Not checked." if tf is None else detail, f"#sales_ledger?{hash_}")
    tf_ = tf or {}
    # None means "unknown" (a gather failed, or no data source yet): shown open with an honest detail, never done.
    q, d, u = (None if tf_.get(k) is None else int(tf_[k]) for k in ("queue_waiting", "drift_accounts", "untied_1099b"))
    wash = str(tf_.get("wash_state") or "never")
    saved = bool(tf_.get("carryforward_saved"))
    drift = step("resolve_log_drift", "Resolve log drift", "tab=fix&sec=health", d == 0,
                 _COULD_NOT_CHECK if d is None else f"The transaction log and the holdings differ in {d} account(s)." if d
                 else "The transaction log agrees with the holdings.")
    if tf is not None and tf_.get("log_in_use") is False:
        drift = {**drift, "state": "na", "detail": "The transaction log is not in use."}
    return [
        step("clear_sales_queue", "Clear the sales waiting for lots", "tab=fix&sec=queue", q == 0,
             _COULD_NOT_CHECK if q is None else f"{q} sale(s) are waiting for lots." if q else "No sales are waiting for lots."),
        drift,
        step("run_wash_check", "Run the wash-sale check", "tab=tax&sec=wash", wash == "clean",
             f"{_WASH_DETAIL.get(wash, _WASH_DETAIL['never'])} This app's accounts only."),
        {**step("tie_1099b", "Apply and tie the broker 1099-B", "tab=tax&sec=b1099", u == 0 or (u is None and tied_confirmed),
             ("You confirmed each 1099-B is tied. Re-check after any new import." if tied_confirmed else
              "Not verified automatically — compare each broker 1099-B on the Import tab.") if u is None else
             f"{u} account(s) do not tie to the broker 1099-B." if u else f"Every account ties to its {year} 1099-B."),
                 "count_known": u is not None},
        step("confirm_carryforward", "Confirm the capital-loss carryforward", "tab=tax&sec=wash", saved,
             f"The carryforward into {year} is saved." if saved else
             f"Enter the capital-loss carryforward into {year} from the prior year's Schedule D (zero if none)."),
    ]


def _growth_roles() -> frozenset[str]:
    from . import ytd_tracking
    return ytd_tracking.GROWTH_ROLES


def _year_of(value: Any) -> int:
    d = str(value or "")
    return int(d[:4]) if d[:4].isdigit() else 0


def build(year: int, *, store: Any, ledgers: Mapping[str, list[Mapping[str, Any]]], snapshots: Sequence[Mapping[str, Any]],
          imports: Sequence[Mapping[str, Any]], setup_rows: Sequence[Mapping[str, Any]],
          cash_differences: Sequence[tuple[str, float | None]], reference_stale: int,
          tax_filing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The checklist for closing ``year``. Inputs are plain data so the whole thing is testable without a plan file.
    ``tax_filing`` (``queue_waiting``, ``drift_accounts``, ``wash_state`` clean|flagged|stale|never, ``untied_1099b``,
    ``carryforward_saved``, optional ``log_in_use``) drives the Sales Ledger tax-filing steps; None leaves them not
    applicable. A count of None means unknown and shows the step open; ``log_in_use`` False makes the drift step ``na``."""
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
    out.extend(_tax_filing_steps(year, tax_filing, is_confirmed(store, year, "tie_1099b")))

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


def _safe(name: str, fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001 - one failing source must not take the checklist down
        log.exception("year-end: could not gather %s; showing the safe default", name)
        return default


def _tax_filing(store: Any, year: int) -> dict[str, Any]:
    """The Sales Ledger state behind the tax-filing steps, read from the caller's open store with the same logic as the
    routes: the queue (``/api/sales/candidates?state=unmatched``), the log drift (``/api/transactions/log``), the wash
    marker plus the year's flags, and the carryforward ``entered`` flag of ``/api/sales/tax-year``."""
    from . import sales_tax_year, transactions

    in_use = _safe("whether the transaction log is in use", lambda: transactions.started(store), None)

    def drift() -> int | None:
        return None if in_use is None else len({d["account"] for d in transactions.reconcile(store)}) if in_use else 0

    def wash() -> str:
        sales = store.sales.list_sales()
        if sales_tax_year.wash_flagged(sales, year):
            return "flagged"
        run = sales_tax_year.wash_run_status(store, sales)
        return "never" if run["never_run"] else "stale" if run["stale"] else "clean"

    # A failed gather yields None (unknown -> the step shows open), never a 0 that would read as done.
    return {"queue_waiting": _safe("the sales queue", lambda: len(store.sales.list_candidates(state="unmatched")), None),
            "drift_accounts": _safe("the log drift", drift, None),
            "log_in_use": in_use,
            "wash_state": _safe("the wash-sale check", wash, "never"),
            # TODO(Task 15): per-account 1099-B tie data does not exist yet; count untied accounts once it does.
            "untied_1099b": None,
            "carryforward_saved": _safe("the carryforward", lambda: store.sales.adjustment(year) is not None, False)}


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
                     cash_differences=[(a["account"], a["difference"]) for a in view["accounts"]], reference_stale=_reference_stale(),
                     tax_filing=_tax_filing(store, year))
