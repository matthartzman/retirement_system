"""Pure capital gain/loss netting for the realized-sales ledger (plan section 7.1). No I/O.

``net_realized_year`` nets one tax year; ``net_realized_by_year`` chains years from ledger rows and the
entered ``realized_adjustments``; ``realized_gain_tax`` prices a netted year by calling the existing federal,
NIIT and state functions (nothing is re-implemented here).

Conventions: carryforwards are positive loss magnitudes. ``net_st`` / ``net_lt`` are each bucket after its own
carryforward and before cross-netting. A loss that is deducted against ordinary income uses the short-term
bucket first, as the Schedule D carryover worksheet does, and the rest carries forward with its character.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .core import (
    compute_fed_tax, ltcg_tax_on_gain, niit_tax, state_for_year, state_income_tax,
)
from .taxes import CAPITAL_LOSS_ORDINARY_LIMIT, capital_loss_ordinary_limit

# The 1211(b) ordinary-income limit is shared with the engine's loss waterfall (taxes.py), never re-typed here.
ORDINARY_LOSS_LIMIT = CAPITAL_LOSS_ORDINARY_LIMIT


def net_realized_year(st_gain: float, lt_gain: float, carryforward_st: float = 0.0,
                      carryforward_lt: float = 0.0, filing: str = "MFJ") -> dict[str, float]:
    """Net one tax year's taxable-account gains (``st_gain``/``lt_gain`` are signed sums) per section 7.1."""
    net_st = float(st_gain) - max(0.0, float(carryforward_st))
    net_lt = float(lt_gain) - max(0.0, float(carryforward_lt))
    total = net_st + net_lt
    out = {"net_st": net_st, "net_lt": net_lt, "ordinary_offset": 0.0, "carryforward_st": 0.0,
           "carryforward_lt": 0.0, "gain_to_tax_ordinary": 0.0, "gain_to_tax_ltcg": 0.0}
    if total >= 0:
        # Cross-net: a bucket loss cancels the other bucket's gain; what is left keeps that bucket's character.
        if net_st > 0:
            out["gain_to_tax_ordinary"] = min(net_st, total)
        if net_lt > 0:
            out["gain_to_tax_ltcg"] = min(net_lt, total)
        return {k: v + 0.0 for k, v in out.items()}
    loss = -total
    offset = min(capital_loss_ordinary_limit(filing), loss)
    out["ordinary_offset"] = offset
    rest = loss - offset
    if net_st < 0 and net_lt < 0:
        # Both buckets losing: the deduction eats short-term first.
        st_used = min(offset, -net_st)
        out["carryforward_st"] = -net_st - st_used
        out["carryforward_lt"] = -net_lt - (offset - st_used)
    elif net_st < 0:  # the other bucket gained, so the whole net loss has short-term character
        out["carryforward_st"] = rest
    else:
        out["carryforward_lt"] = rest
    return {k: v + 0.0 for k, v in out.items()}


def net_realized_by_year(sales: Iterable[Mapping[str, Any]],
                         adjustments: Mapping[int, Mapping[str, Any]] | None = None,
                         filing: str = "MFJ", through_year: int | None = None) -> dict[int, dict[str, float]]:
    """Net every year from the first ledger/adjustment year to the last (or ``through_year``, whichever is
    later), chaining carryforwards so a loss keeps being used in years with no sales.

    ``sales`` rows carry ``tax_year``, ``term`` (``short``/``long``) and ``gain``; voided rows, non-taxable
    classes and rows with no gain are ignored. ``adjustments`` maps year -> ``realized_adjustments`` row
    (``carryforward_short``/``carryforward_long``) and holds the carryforward INTO that year as entered from
    last year's Schedule D; when a year has no entry the previous year's computed carry-out is used.
    """
    adjustments = adjustments or {}
    totals: dict[int, list[float]] = {}
    for row in sales:
        if row.get("status", "confirmed") != "confirmed" or row.get("tax_class", "taxable") != "taxable":
            continue
        gain = row.get("gain")
        term = row.get("term")
        if term not in ("short", "long"):
            raise ValueError(f"term must be 'short' or 'long', got {term!r}")
        if gain is None:
            continue
        year = int(row["tax_year"])
        totals.setdefault(year, [0.0, 0.0])[0 if term == "short" else 1] += float(gain)
    years = set(totals) | {int(y) for y in adjustments}
    last = max(years | ({int(through_year)} if through_year is not None and years else set()), default=0)
    result: dict[int, dict[str, float]] = {}
    if not years:
        return result
    cf_st = cf_lt = 0.0
    for year in range(min(years), last + 1):
        if year in adjustments:
            adj = adjustments[year]
            cf_st = float(adj.get("carryforward_short") or 0.0)
            cf_lt = float(adj.get("carryforward_long") or 0.0)
        st, lt = totals.get(year, (0.0, 0.0))
        result[year] = net_realized_year(st, lt, cf_st, cf_lt, filing)
        cf_st, cf_lt = result[year]["carryforward_st"], result[year]["carryforward_lt"]
    return result


def realized_gain_tax(c: Mapping[str, Any], netting: Mapping[str, float], *, year: int, ordinary_income: float,
                      magi: float, state_rate_override: float | None = None) -> dict[str, float]:
    """Tax on one netted year, using the engine's own functions.

    ``ordinary_income`` is the taxable ordinary income the gains stack on; ``magi`` is the household MAGI
    before these gains. Federal ordinary tax is the increment of ``compute_fed_tax`` for the ordinary-taxed
    gain, less the same measure for the loss deducted against ordinary income (so it can be negative). NIIT
    uses ``niit_tax`` on the net gain; state tax uses ``state_income_tax`` for ``state_for_year(c, year)``.
    """
    filing = str(c.get("filing_status", "MFJ") or "MFJ")
    brk_inf = float(c.get("brk_inf", 0.02) or 0.02)
    ordinary_gain = netting["gain_to_tax_ordinary"]
    ltcg_gain = netting["gain_to_tax_ltcg"]
    offset = netting["ordinary_offset"]
    base = max(0.0, ordinary_income)
    ordinary_tax = 0.0
    if ordinary_gain > 0:
        ordinary_tax = compute_fed_tax(base + ordinary_gain, year, filing, brk_inf) - compute_fed_tax(base, year, filing, brk_inf)
    if offset > 0:
        ordinary_tax -= compute_fed_tax(base, year, filing, brk_inf) - compute_fed_tax(max(0.0, base - offset), year, filing, brk_inf)
    ltcg_tax = ltcg_tax_on_gain(c, ltcg_gain, base + ordinary_gain, year) if ltcg_gain > 0 else 0.0
    net_gain = ordinary_gain + ltcg_gain
    niit = 0.0
    if net_gain > 0 and bool(c.get("model_niit", True)):
        niit = niit_tax(net_gain, magi + net_gain, filing)
    state_tax = 0.0
    if net_gain > 0:
        state_tax = state_income_tax(
            state_for_year(c, year), 0.0, 0.0, 0.0, net_gain, 0.0, 0.0, year,
            age_over_65=True, filing=filing, brk_inf=brk_inf, rate_override=state_rate_override)
    total = ordinary_tax + ltcg_tax + niit + state_tax
    return {"ordinary_tax": ordinary_tax + 0.0, "ltcg_tax": ltcg_tax, "niit": niit, "state_tax": state_tax,
            "total": total + 0.0}
