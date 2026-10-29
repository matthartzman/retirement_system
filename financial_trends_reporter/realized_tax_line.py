"""Tax on gains realized this year (sales ledger plan 7.2 / 9.4), for the Live Snapshot's tax section and the
daily log's ``tax_estimate``.

It nets the taxable-account sales of the year with ``src.realized_tax`` (carryforwards chained from the
``realized_adjustments`` the user entered) and prices the result with the Planner's own tax functions when its
config is readable. It is a line of its own, apart from "tax on unrealized gains if liquidated": a sold lot has
left holdings, so the two never overlap.

Without the Planner's config the same netting is priced at flat rates. The year's ordinary income is not known to
Trends; ``ordinary_income`` is the income recorded so far this year, so the bracket the gains stack on is a
floor and the figure an estimate. Pure: no I/O."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

DEFAULT_ORDINARY_RATE = 0.25
DEFAULT_LTCG_RATE = 0.15


def ledger_rows(sales: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """(rows for ``net_realized_by_year``, taxable confirmed sales left out for want of a holding period)."""
    rows, unknown = [], 0
    for s in sales:
        if s.get("status", "confirmed") != "confirmed" or s.get("tax_class", "taxable") != "taxable" or s.get("gain") is None:
            continue
        term = s.get("holding_period")
        if term not in ("short", "long"):
            unknown += 1
            continue
        rows.append({"tax_year": int(str(s["sale_date"])[:4]), "term": term, "gain": s["gain"], "tax_class": "taxable"})
    return rows, unknown


def line(cfg: Mapping[str, Any] | None, sales: Iterable[Mapping[str, Any]], adjustments: Iterable[Mapping[str, Any]] | None,
         today: date, *, ordinary_income: float = 0.0, ordinary_rate: float = DEFAULT_ORDINARY_RATE,
         ltcg_rate: float = DEFAULT_LTCG_RATE) -> dict[str, Any]:
    from src.realized_tax import net_realized_by_year, realized_gain_tax   # the engine's tax code loads on first use

    year = today.year
    rows, unknown = ledger_rows(sales)
    by_year = {int(a["tax_year"]): a for a in adjustments or []}
    filing = str((cfg or {}).get("filing_status", "MFJ") or "MFJ")
    netting = net_realized_by_year(rows, by_year, filing).get(year)
    if netting is None:   # nothing sold this year and no carryforward entered
        netting = {"net_st": 0.0, "net_lt": 0.0, "ordinary_offset": 0.0, "carryforward_st": 0.0, "carryforward_lt": 0.0,
                   "gain_to_tax_ordinary": 0.0, "gain_to_tax_ltcg": 0.0}
    parts, method = None, "flat"
    if cfg:
        try:
            override = (by_year.get(year) or {}).get("state_rate_override")
            parts = realized_gain_tax(cfg, netting, year=year, ordinary_income=ordinary_income, magi=ordinary_income,
                                      state_rate_override=override)
            method = "planner"
        except Exception:  # noqa: BLE001 - a partial plan must not take the page or the log down
            parts = None
    if parts is None:
        ordinary = netting["gain_to_tax_ordinary"] * ordinary_rate - netting["ordinary_offset"] * ordinary_rate
        ltcg = netting["gain_to_tax_ltcg"] * ltcg_rate
        parts = {"ordinary_tax": ordinary, "ltcg_tax": ltcg, "niit": 0.0, "state_tax": 0.0, "total": ordinary + ltcg}
    return {"method": method, "tax_year": year,
            "st_gain": round(sum(r["gain"] for r in rows if r["tax_year"] == year and r["term"] == "short"), 2),
            "lt_gain": round(sum(r["gain"] for r in rows if r["tax_year"] == year and r["term"] == "long"), 2),
            "carryforward_st": round(netting["carryforward_st"], 2), "carryforward_lt": round(netting["carryforward_lt"], 2),
            "ordinary_offset": round(netting["ordinary_offset"], 2),
            **{k: round(parts[k], 2) for k in ("ordinary_tax", "ltcg_tax", "niit", "state_tax", "total")},
            "unknown_term": {"count": unknown}}
