"""Year-to-date realized figures for the 5 pm daily log entry (sales ledger plan 9.3).

``realized_ytd`` is written only when the ledger could be read: an entry without it (any entry from before the
ledger, or a day the plan could not be opened) reads as "no data" through ``trends_log.realized_ytd_of``, never as
zero. Taxable accounts only (they alone create tax events); confirmed sales only. The "include unconfirmed
(estimate)" figures of the Realized view are never logged; waiting sales are only counted and totalled.

Key names matter to the percent view: dollar fields are left unlisted so they are scaled with everything else,
and the count sits under the allowlisted ``count`` key. Do not add ``_pct``/``_rate`` suffixes to dollar fields."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from . import realized_tax_line, realized_view


def from_rows(sales: list[dict], candidates: list[dict], today: date, *, adjustments: list[dict] | None = None,
              cfg: dict | None = None, ordinary_income: float = 0.0) -> dict[str, Any]:
    """The logged block from ledger rows. Pure. ``tax_estimate`` is the realized-tax line's total (Planner method when
    ``cfg`` is its config, else flat default rates; see ``realized_tax_line``)."""
    jan1 = date(today.year, 1, 1)
    built = realized_view.build(sales=sales, candidates=candidates, lots=[], today=today, start=jan1.isoformat(), taxable_only=True)
    s = built["summary"]
    waiting = [c for c in candidates if realized_view._in(c["sale_date"], jan1, today)]
    amount = sum(abs(float(c["amount"])) for c in waiting if c.get("amount") is not None)
    return {"year": today.year, "st_gain": s["st_gain"], "lt_gain": s["lt_gain"], "net": s["net"],
            "tax_estimate": realized_tax_line.line(cfg, sales, adjustments, today, ordinary_income=ordinary_income)["total"],
            "wash_flagged": s["wash_flagged"],
            "unconfirmed": {"count": len(waiting), "amount": round(amount, 2)}}


def realized_ytd(base_dir: str | Path, today: date, *, ytd_income: float | None = None) -> dict[str, Any] | None:
    """The block for today's log entry, or None when the plan (or its ledger tables) cannot be read.
    ``ytd_income`` is the income recorded so far this year (the bracket the gains stack on)."""
    try:
        from src import active_plan

        with active_plan.workspace_store(Path(base_dir)) as store:
            sales, candidates = store.sales.list_sales(), store.sales.list_candidates(state="unmatched")
            adjustments = store.sales.adjustments()
    except Exception:  # noqa: BLE001 - no plan, locked, or older than the ledger: no data, not zeros
        return None
    from .live_snapshot import planner_config, _num

    return from_rows(sales, candidates, today, adjustments=adjustments, cfg=planner_config(Path(base_dir)),
                     ordinary_income=_num(ytd_income))
