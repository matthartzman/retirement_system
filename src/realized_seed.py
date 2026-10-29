"""What the realized-sales ledger hands the projection for year 1 (plan section 7.3, step 3b.1). Pure, no I/O.

``build_realized_seed`` nets the plan year with ``realized_tax`` and returns ``None`` (the empty-ledger guard:
nothing is added anywhere, so output is unchanged) or ``{year, gain_ordinary, gain_ltcg, loss_pool}``:

* ``gain_ordinary`` - net short-term gain left after netting; the engine adds it to ordinary investment income.
* ``gain_ltcg`` - net long-term gain left after netting; the engine adds it to the realized-gain line that already
  carries home and rental sale gains (so it reaches AGI, NIIT and IRMAA MAGI and is taxed as LTCG).
* ``loss_pool`` - the net capital loss (carryforward in plus the year's losses, as one magnitude); it seeds
  ``cap_loss_carryforward``, so the engine's own waterfall offsets simulated gains first, then takes its ordinary
  offset, then rolls the rest forward. Short/long character is collapsed (documented v1 limit).

A year has either gains or a pool, never both: netting leaves one or the other.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .realized_tax import net_realized_by_year

_TERMS = ("short", "long")


def terms_from_ledger_rows(sales: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Ledger rows as the ``{tax_year, term, gain, status, tax_class}`` records ``realized_tax`` nets."""
    return [{"tax_year": int(s["sale_date"][:4]), "term": s["holding_period"], "gain": s["gain"],
             "status": s["status"], "tax_class": s["tax_class"]}
            for s in sales if s["holding_period"] in _TERMS]


def build_realized_seed(sales: Iterable[Mapping[str, Any]], adjustments: Mapping[int, Mapping[str, Any]],
                        year: int, filing: str = "MFJ") -> dict[str, Any] | None:
    year = int(year)
    terms = terms_from_ledger_rows(sales)
    live = [t for t in terms if t["status"] == "confirmed" and t["tax_class"] == "taxable"
            and t["gain"] is not None and t["tax_year"] == year]
    by_year = net_realized_by_year(terms, adjustments, filing, through_year=year)
    prev = by_year.get(year - 1)
    if year in adjustments:
        cf_in = float(adjustments[year].get("carryforward_short") or 0.0) + float(adjustments[year].get("carryforward_long") or 0.0)
    else:
        cf_in = (prev["carryforward_st"] + prev["carryforward_lt"]) if prev else 0.0
    if not live and cf_in == 0.0:
        return None
    n = by_year[year]
    total = n["net_st"] + n["net_lt"]
    return {"year": year, "gain_ordinary": n["gain_to_tax_ordinary"] + 0.0, "gain_ltcg": n["gain_to_tax_ltcg"] + 0.0,
            "loss_pool": (-total if total < 0 else 0.0) + 0.0}


def active_realized_seed(year: int, filing: str = "MFJ") -> dict[str, Any] | None:
    """``build_realized_seed`` for the active plan's own ledger (``None`` when the plan has none)."""
    from . import active_plan
    sales, adjustments = active_plan.peek_sales_ledger()
    return build_realized_seed(sales, adjustments, year, filing)
