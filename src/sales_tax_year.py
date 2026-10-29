"""Realized-sales ledger, server side of the Sales Ledger page's tax-year panel (plan step 3a.3): the year's
capital gain/loss netting, the carryforward entry and the possible-wash flags. Netting is ``realized_tax`` and
detection is ``wash_sales``; this module only reads and writes the plan file. Nothing here changes the
projection or the engine. Every function takes the workspace ``input`` folder like ``sales_service``."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from . import active_plan
from .core import ACCOUNT_TYPES, _infer_type
from .realized_seed import terms_from_ledger_rows
from .realized_tax import net_realized_by_year, net_realized_year
from .taxes import capital_loss_ordinary_limit
from .sales_ledger import ValidationError
from .wash_sales import buys_from_rows, detect_wash_sales, plan_flag_updates

_LEDGER_CLASSES = ("taxable", "pre_tax", "roth", "hsa")


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _filing(input_dir: str | Path, filing: str | None) -> str:
    if filing is None:
        filing = active_plan.peek_plan_data_for_input_dir(input_dir).get("Household", {}).get("", {}).get("filing_status")
    return "MFS" if str(filing or "").strip().upper() == "MFS" else (str(filing or "MFJ").strip().upper() or "MFJ")


def _adjustments(store) -> dict[int, dict[str, Any]]:
    return {int(a["tax_year"]): a for a in store.sales.adjustments()}


def tax_year_summary(input_dir: str | Path, year: int, *, filing: str | None = None) -> dict[str, Any]:
    """Netting for ``year`` with the carryforward chained from earlier years (an entered figure for a year
    replaces the computed one), the raw short/long sums, and the wash-flagged losses."""
    year = int(year)
    filing = _filing(input_dir, filing)
    with active_plan.workspace_store(_base(input_dir)) as store:
        sales = store.sales.list_sales()
        adjustments = _adjustments(store)
    by_year = net_realized_by_year(terms_from_ledger_rows(sales), adjustments, filing, through_year=year)
    prev = by_year.get(year - 1)
    entered = year in adjustments
    if entered:
        cf_in = (float(adjustments[year]["carryforward_short"]), float(adjustments[year]["carryforward_long"]))
    else:
        cf_in = (prev["carryforward_st"], prev["carryforward_lt"]) if prev else (0.0, 0.0)
    netting = by_year.get(year) or net_realized_year(0.0, 0.0, 0.0, 0.0, filing)
    live = [s for s in sales if s["status"] == "confirmed" and s["tax_class"] == "taxable"
            and s["gain"] is not None and s["sale_date"][:4] == str(year)]
    flagged = [s for s in live if s["wash_flag"] != "none" and s["gain"] < 0]
    return {
        "year": year, "filing": filing, "limit": capital_loss_ordinary_limit(filing), "netting": netting,
        "carryforward_in": {"short": cf_in[0] + 0.0, "long": cf_in[1] + 0.0, "entered": entered},
        "carryforward_out": {"short": netting["carryforward_st"], "long": netting["carryforward_lt"]},
        "totals": {"count": len(live),
                   "st_gain": sum(s["gain"] for s in live if s["holding_period"] == "short") + 0.0,
                   "lt_gain": sum(s["gain"] for s in live if s["holding_period"] == "long") + 0.0},
        "wash": {"count": len(flagged), "flagged_loss": sum(-s["gain"] for s in flagged) + 0.0,
                 "rows": [{"sale_id": s["sale_id"], "symbol": s["symbol"], "sale_date": s["sale_date"],
                           "gain": s["gain"], "flag": s["wash_flag"], "note": s["wash_note"]} for s in flagged]},
    }


def _figure(name: str, value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(out) or out < 0:
        raise ValidationError(f"{name} must be zero or more (enter the loss as a positive amount)")
    return out


def set_carryforward(input_dir: str | Path, year: int, *, short: Any, long: Any) -> dict[str, Any]:
    """Enter the capital-loss carryforward INTO ``year`` from the prior year's Schedule D (positive amounts)."""
    try:
        year = int(year)
    except (TypeError, ValueError):
        raise ValidationError(f"year must be a number, got {year!r}") from None
    if not 1990 <= year <= 2100:
        raise ValidationError("year must be between 1990 and 2100")
    short_f, long_f = _figure("short-term carryforward", short), _figure("long-term carryforward", long)
    with active_plan.workspace_store(_base(input_dir), write=True) as store:
        existing = store.sales.adjustment(year) or {}
        store.sales.set_adjustment(year, carryforward_short=short_f, carryforward_long=long_f,
                                   state_rate_override=existing.get("state_rate_override"))
    return {"year": year, "carryforward_short": short_f, "carryforward_long": long_f}


def _account_classes(sales: list[dict[str, Any]], accounts: set[str]) -> dict[str, dict[str, str]]:
    """Tax class per account for the IRA message: a class the user gave a ledger row wins, else the Planner's
    own naming rule (``core._infer_type`` suffixes); an account matching neither is left unclassified."""
    ledger = {s["account"]: s["tax_class"] for s in sales}
    out: dict[str, dict[str, str]] = {}
    for name in accounts:
        cls = ledger.get(name)
        if cls is None:
            try:
                cls = ACCOUNT_TYPES[_infer_type(name)]["tax"]
            except ValueError:
                cls = None
        if cls in _LEDGER_CLASSES:
            out[name] = {"label": name, "tax_class": cls}
    return out


def refresh_wash_flags(input_dir: str | Path) -> dict[str, int]:
    """Re-run the possible-wash scan against the holdings lots and write the flags to the ledger rows.
    Returns how many loss sales are flagged and how many rows changed."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        sales = store.sales.list_sales()
        buys = buys_from_rows(store.dataset("holdings").rows(), source="holdings")
        detected = detect_wash_sales(sales, buys, accounts=_account_classes(sales, {b["account"] for b in buys}))
        updates = plan_flag_updates(sales, detected)
        for sale_id, flag, note in updates:
            store.sales.set_wash_flag(sale_id, flag, note)
    return {"flagged": len(detected), "updated": len(updates)}
